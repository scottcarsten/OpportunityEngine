"""Manually-started Telegram command listener (OE-ADR-035).

Long-polls Telegram's getUpdates API and replies to /status, /pending,
/new, /newsearch from Scott's configured chat only - every other chat
is silently ignored. This is a command dispatcher, not a chatbot: no
AI, no open-ended replies, just scripted lookups against the same data
the dashboard shows.

Run with:
    python -m backend.telegram_bot
Leave it running in a terminal/tmux/screen on an always-on machine.
Stop with Ctrl+C.
"""

import logging
import sys
from pathlib import Path

import httpx

from backend.cli import ADAPTERS
from backend.config import Settings, get_settings
from backend.database import Database
from backend.jobs import run_collection
from backend.logging_config import configure_logging
from backend.notifications import send_telegram
from backend.services.constitution_service import Constitution, load_constitution
from backend.services.opportunity_service import OpportunityService
from backend.services.reporting_service import ReportingService

_USAGE_TEXT = "Unknown command. Try /status, /pending, /new, or /newsearch."
_MAX_LISTED = 10
_LOG_FILE = Path("data/logs/telegram_bot.log")

logger = logging.getLogger(__name__)


def get_updates(
    bot_token: str, offset: int | None, *, timeout: int = 30, client: httpx.Client | None = None
) -> list[dict]:
    """Long-poll Telegram for new updates since `offset`."""
    params: dict[str, int] = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset
    owns_client = client is None
    http_client = client or httpx.Client(timeout=timeout + 10)
    try:
        response = http_client.get(
            f"https://api.telegram.org/bot{bot_token}/getUpdates", params=params
        )
        response.raise_for_status()
        return response.json().get("result", [])
    finally:
        if owns_client:
            http_client.close()


def _format_opportunities(rows: list[dict], empty_message: str) -> str:
    if not rows:
        return empty_message
    lines = []
    for row in rows[:_MAX_LISTED]:
        organization = row.get("organization_name") or "Unspecified organization"
        lines.append(f"- {row['title']} ({organization}) - {row['age_days']}d old")
    remaining = len(rows) - _MAX_LISTED
    if remaining > 0:
        lines.append(f"...and {remaining} more.")
    return "\n".join(lines)


def _format_status(reporting_service: ReportingService) -> str:
    report = reporting_service.build_report()
    counts = {row["status"]: row["count"] for row in report["by_status"]}
    pending = counts.get("new", 0) + counts.get("eligible", 0)
    last_run_times = [row["last_run_at"] for row in report["by_source"] if row["last_run_at"]]
    last_collected = max(last_run_times) if last_run_times else "never"
    return "\n".join(
        [
            "OpportunityEngine status:",
            f"- {pending} pending review (new/eligible)",
            f"- {counts.get('shortlisted', 0)} shortlisted, "
            f"{counts.get('preparing', 0)} preparing",
            f"- Last collection: {last_collected}",
        ]
    )


def _format_pending(opportunity_service: OpportunityService) -> str:
    rows = opportunity_service.list_opportunities(
        lifecycle_status="new"
    ) + opportunity_service.list_opportunities(lifecycle_status="eligible")
    rows.sort(key=lambda row: row["created_at"], reverse=True)
    return _format_opportunities(rows, "Nothing pending review right now.")


def _format_new(opportunity_service: OpportunityService) -> str:
    rows = opportunity_service.list_opportunities(lifecycle_status="new")
    return _format_opportunities(rows, "No newly-collected opportunities awaiting triage.")


def _run_newsearch(database: Database, constitution: Constitution) -> str:
    summaries = []
    for name, adapter_cls in ADAPTERS.items():
        try:
            result = run_collection(database, constitution, adapter_cls())
            summaries.append(
                f"{name}: {result['status']}, {result['records_created']} new "
                f"of {result['records_seen']} seen"
            )
        except Exception as exc:  # noqa: BLE001 - report, don't crash the listener
            summaries.append(f"{name}: failed ({exc})")
    return "Collection complete:\n" + "\n".join(summaries)


def dispatch_command(
    command: str,
    database: Database,
    constitution: Constitution,
    bot_token: str,
    chat_id: str,
) -> str:
    """Handle one recognized command and return the reply text."""
    if command == "/status":
        return _format_status(ReportingService(database))
    if command == "/pending":
        return _format_pending(OpportunityService(database, constitution))
    if command == "/new":
        return _format_new(OpportunityService(database, constitution))
    if command == "/newsearch":
        send_telegram(bot_token, chat_id, "Starting collection across all sources, hang tight...")
        return _run_newsearch(database, constitution)
    return _USAGE_TEXT


def handle_update(
    update: dict,
    allowed_chat_id: str,
    database: Database,
    constitution: Constitution,
    bot_token: str,
) -> tuple[str | None, str | None]:
    """Return (reply_text, chat_id) to send, or (None, None) to send nothing.

    Any chat other than `allowed_chat_id` is silently ignored - no reply,
    so a stranger who somehow messages the bot doesn't even learn it
    responds to commands.
    """
    message = update.get("message")
    if not message:
        return None, None
    chat_id = str(message.get("chat", {}).get("id", ""))
    if chat_id != allowed_chat_id:
        return None, None
    text = (message.get("text") or "").strip()
    if not text.startswith("/"):
        return None, None
    command = text.split()[0].lower()
    reply = dispatch_command(command, database, constitution, bot_token, chat_id)
    return reply, chat_id


def main(settings: Settings | None = None) -> int:
    settings = settings or get_settings()

    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        print(
            "Telegram isn't configured - set OPPORTUNITY_ENGINE_TELEGRAM_BOT_TOKEN "
            "and OPPORTUNITY_ENGINE_TELEGRAM_CHAT_ID in .env."
        )
        return 1

    constitution = load_constitution(settings.constitution_path)
    database = Database(database_path=settings.database_path)
    database.initialize()

    # Configured after database.initialize(), not before: Alembic's
    # migration runner calls logging.config.fileConfig() on alembic.ini
    # (database/migrations/env.py), which resets the root logger and
    # would silently wipe out our handlers if we configured them first.
    configure_logging(settings.log_level, log_file=_LOG_FILE)

    offset: int | None = None
    logger.info("Telegram listener started.")
    print(f"Telegram listener started, logging to {_LOG_FILE}. Ctrl+C to stop.")
    try:
        while True:
            try:
                updates = get_updates(settings.telegram_bot_token, offset)
            except httpx.HTTPError as exc:
                # A transient network blip shouldn't kill an unattended
                # process - log it and keep polling.
                logger.warning("getUpdates failed, retrying: %s", exc)
                continue

            for update in updates:
                offset = update["update_id"] + 1
                message_text = (update.get("message") or {}).get("text", "")
                try:
                    reply, chat_id = handle_update(
                        update,
                        settings.telegram_chat_id,
                        database,
                        constitution,
                        settings.telegram_bot_token,
                    )
                except Exception:
                    logger.exception("Error handling update %s (%r)", update["update_id"], message_text)
                    continue

                if reply and chat_id:
                    logger.info("Handled command %r", message_text)
                    sent, error = send_telegram(settings.telegram_bot_token, chat_id, reply)
                    if not sent:
                        logger.warning("Failed to send reply: %s", error)
    except KeyboardInterrupt:
        logger.info("Telegram listener stopped (Ctrl+C).")
        print("Stopped.")
    finally:
        database.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
