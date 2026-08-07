"""Telegram command listener (OE-ADR-035, OE-ADR-036, OE-ADR-037, OE-ADR-039).

Long-polls Telegram's getUpdates API and replies to /status, /pending,
/new, /newsearch from Scott's configured chat only - every other chat
is silently ignored. This is a command dispatcher, not a chatbot: no
AI, no open-ended replies, just scripted lookups against the same data
the dashboard shows.

Also runs a full collection+sweep cycle across every source on its own,
every `background_check_interval_minutes` (default 30), without
needing /newsearch - the project's actual background scheduler. Stays
silent on a normal run; only messages Scott if something failed.

And, if configured, checks a dedicated job-search mailbox for new
employer replies every `mail_check_interval_minutes` (default 10) via
Microsoft Graph - alerts on everything, since that inbox is blank and
dedicated, and best-effort correlates each message to an applied
opportunity without ever gating the alert on a successful match. A
failed mail check (expired Graph auth, a network error) also alerts,
rather than failing silently.

Runs as a systemd user service (see `systemd/`); `Restart=on-failure`
recovers from a crash automatically, and `OnFailure=` alerts Scott via
Telegram if it crash-loops and systemd gives up retrying.

Manual/dev use:
    python -m backend.telegram_bot
Stop with Ctrl+C.
"""

import logging
import sys
import time
from pathlib import Path

import httpx

from backend.cli import ADAPTERS
from backend.config import Settings, get_settings
from backend.database import Database
from backend.db.models import Notification
from backend.graph_mail import GraphAuthExpiredError, check_mail
from backend.jobs import run_collection
from backend.logging_config import configure_logging
from backend.notifications import send_telegram
from backend.services.constitution_service import Constitution, load_constitution
from backend.services.opportunity_service import OpportunityService
from backend.services.reporting_service import ReportingService
from backend.timeutil import now_iso

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


def run_periodic_collection(database: Database, constitution: Constitution) -> str | None:
    """Run a full collection+sweep cycle across every adapter.

    Returns an alert message only if something actually failed - a
    normal "nothing new" run stays silent. Per-opportunity notifications
    (already wired into ingest, OE-ADR-029) are what surface anything
    actually worth Scott's attention; a periodic status ping every N
    minutes regardless of findings would just be noise.
    """
    summary = _run_newsearch(database, constitution)
    logger.info("Periodic collection: %s", summary.replace("\n", " | "))
    if "failed" in summary:
        return f"Periodic check found a problem:\n{summary}"
    return None


def run_mail_check(database: Database, constitution: Constitution, settings: Settings) -> None:
    """Check the job-search mailbox and alert on both new messages and
    failures (OE-ADR-039) - a mail-check failure used to be swallowed
    (logged only); now it alerts the same way a failed collection run
    already does, with a distinct message when Graph auth has expired
    since that needs a specific fix (re-running `python -m
    backend.graph_mail` by hand), not just a retry.
    """
    alerts: list[dict] = []
    try:
        alerts = check_mail(database, constitution, settings)
    except GraphAuthExpiredError:
        logger.warning("Graph auth expired; alerting.")
        sent, error = send_telegram(
            settings.telegram_bot_token,
            settings.telegram_chat_id,
            "Graph mail auth expired - run `python -m backend.graph_mail` "
            "on the server to re-authenticate.",
        )
        if not sent:
            logger.warning("Failed to send auth-expired alert: %s", error)
    except Exception as exc:
        logger.exception("Mail check failed unexpectedly.")
        sent, error = send_telegram(
            settings.telegram_bot_token,
            settings.telegram_chat_id,
            f"Mail check failed: {exc}",
        )
        if not sent:
            logger.warning("Failed to send mail-check-failure alert: %s", error)

    for alert in alerts:
        sent, error = send_telegram(
            settings.telegram_bot_token, settings.telegram_chat_id, alert["text"]
        )
        if not sent:
            logger.warning("Failed to send mail alert: %s", error)
        with database.session() as session:
            session.add(
                Notification(
                    opportunity_id=alert["opportunity_id"],
                    notification_type="employer_reply",
                    channel="telegram",
                    status="sent" if sent else "failed",
                    subject=alert["subject"],
                    body=alert["body"],
                    sent_at=now_iso() if sent else None,
                    error_summary=error,
                )
            )
            session.commit()


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
    interval_seconds = settings.background_check_interval_minutes * 60
    next_check = time.monotonic()  # due immediately on startup
    mail_interval_seconds = settings.mail_check_interval_minutes * 60
    next_mail_check = time.monotonic()  # due immediately on startup
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

            if interval_seconds > 0 and time.monotonic() >= next_check:
                logger.info("Running periodic collection check.")
                alert = run_periodic_collection(database, constitution)
                if alert:
                    sent, error = send_telegram(
                        settings.telegram_bot_token, settings.telegram_chat_id, alert
                    )
                    if not sent:
                        logger.warning("Failed to send periodic alert: %s", error)
                next_check = time.monotonic() + interval_seconds

            if mail_interval_seconds > 0 and time.monotonic() >= next_mail_check:
                logger.info("Running mail check.")
                run_mail_check(database, constitution, settings)
                next_mail_check = time.monotonic() + mail_interval_seconds
    except KeyboardInterrupt:
        logger.info("Telegram listener stopped (Ctrl+C).")
        print("Stopped.")
    finally:
        database.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
