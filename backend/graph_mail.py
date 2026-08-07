"""Read-only employer-reply monitoring via Microsoft Graph (OE-ADR-037).

Watches a dedicated, isolated mailbox (lonestaritservices@outlook.com)
for new mail via Graph's delta query, alerts on every new message
(the inbox is blank and dedicated, so anything arriving is relevant),
and best-effort correlates each one to an opportunity Scott has
actually applied to. A failed correlation never suppresses an alert -
it just means the alert says "unmatched" instead of naming a company.

Read-only: only the Mail.Read scope is ever requested. Nothing here
sends, deletes, or modifies anything, so - unlike a future integration
that actually acts on Scott's behalf - this never goes through
ApprovalService (OE-ADR-033's gating principle governs restricted
actions; reading a mailbox isn't one, same reasoning as self-notifying
via ntfy/Telegram, OE-ADR-029).
"""

import logging
from pathlib import Path
from typing import Any

import httpx
import msal

from backend.config import Settings
from backend.database import Database
from backend.services.constitution_service import Constitution
from backend.services.opportunity_service import OpportunityService

logger = logging.getLogger(__name__)

_SCOPES = ["Mail.Read"]
_DELTA_URL = "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta"


def _build_app(settings: Settings) -> tuple[msal.PublicClientApplication, msal.SerializableTokenCache]:
    cache = msal.SerializableTokenCache()
    if settings.graph_token_cache_path.exists():
        cache.deserialize(settings.graph_token_cache_path.read_text())
    app = msal.PublicClientApplication(
        client_id=settings.ms_graph_client_id,
        authority=f"https://login.microsoftonline.com/{settings.ms_graph_tenant_id}",
        token_cache=cache,
    )
    return app, cache


def _save_cache(cache: msal.SerializableTokenCache, path: Path) -> None:
    if cache.has_state_changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(cache.serialize())


def get_access_token(settings: Settings) -> str | None:
    """Return a valid Graph access token, refreshing silently when possible.

    Falls back to an interactive device-code flow only when no cached
    account exists (first run, or a revoked/expired refresh token) -
    prints a one-time sign-in URL/code for Scott to complete in a
    browser. Never raises; returns None on any failure so a caller can
    log and retry next cycle instead of crashing.
    """
    app, cache = _build_app(settings)
    try:
        accounts = app.get_accounts()
        result = None
        if accounts:
            result = app.acquire_token_silent(_SCOPES, account=accounts[0])
        if not result:
            flow = app.initiate_device_flow(scopes=_SCOPES)
            if "user_code" not in flow:
                logger.error(
                    "Failed to start Graph device-code flow: %s",
                    flow.get("error_description", flow),
                )
                return None
            print(flow["message"], flush=True)
            logger.info("Waiting for Graph device-code sign-in to complete...")
            result = app.acquire_token_by_device_flow(flow)
        if result and "access_token" in result:
            return result["access_token"]
        logger.error(
            "Graph authentication failed: %s",
            result.get("error_description") if result else "no result",
        )
        return None
    finally:
        _save_cache(cache, settings.graph_token_cache_path)


def fetch_new_messages(
    access_token: str, delta_link_path: Path, *, client: httpx.Client | None = None
) -> list[dict[str, Any]]:
    """Return messages new since the last check via Graph's delta query.

    The first-ever call (no persisted delta link) has nothing to compare
    against, so Graph returns everything currently in the inbox as
    "changes" - that's a baseline, not new mail, so this returns an
    empty list on that call while still persisting the resulting delta
    link for next time. Every later call only returns genuinely new
    messages.
    """
    is_first_run = not delta_link_path.exists()
    url: str | None = delta_link_path.read_text().strip() if not is_first_run else _DELTA_URL
    owns_client = client is None
    http_client = client or httpx.Client(timeout=15.0)
    messages: list[dict[str, Any]] = []
    try:
        headers = {"Authorization": f"Bearer {access_token}"}
        while url:
            response = http_client.get(url, headers=headers)
            response.raise_for_status()
            payload = response.json()
            messages.extend(payload.get("value", []))
            if "@odata.nextLink" in payload:
                url = payload["@odata.nextLink"]
            elif "@odata.deltaLink" in payload:
                delta_link_path.parent.mkdir(parents=True, exist_ok=True)
                delta_link_path.write_text(payload["@odata.deltaLink"])
                url = None
            else:
                url = None
    finally:
        if owns_client:
            http_client.close()
    return [] if is_first_run else messages


def correlate_opportunity(message: dict[str, Any], applied_opportunities: list[dict[str, Any]]) -> int | None:
    """Best-effort match a message's sender to an applied opportunity's
    organization, by domain or display name. Never raises; returns None
    on no match - this only enriches an alert, it never gates one."""
    sender = (message.get("from") or {}).get("emailAddress") or {}
    sender_address = (sender.get("address") or "").lower()
    sender_name = (sender.get("name") or "").lower()
    sender_domain = sender_address.split("@")[-1] if "@" in sender_address else ""
    domain_root = sender_domain.split(".")[0] if sender_domain else ""

    for opportunity in applied_opportunities:
        organization = (opportunity.get("organization_name") or "").lower()
        normalized_org = "".join(ch for ch in organization if ch.isalnum())
        if not normalized_org:
            continue
        normalized_domain_root = domain_root.replace("-", "")
        if (
            (normalized_domain_root and normalized_org in normalized_domain_root)
            or (normalized_domain_root and normalized_domain_root in normalized_org)
            or (sender_name and normalized_org in sender_name.replace(" ", ""))
        ):
            return opportunity["id"]
    return None


def format_mail_alert(message: dict[str, Any], matched_opportunity: dict[str, Any] | None) -> str:
    sender = (message.get("from") or {}).get("emailAddress") or {}
    sender_display = sender.get("name") or sender.get("address") or "Unknown sender"
    subject = message.get("subject") or "(no subject)"
    preview = message.get("bodyPreview") or ""

    lines = [f"New email in job-search inbox from {sender_display}", f"Subject: {subject}"]
    if matched_opportunity:
        organization = matched_opportunity.get("organization_name") or "an unspecified organization"
        lines.append(f"Possibly related to: {matched_opportunity['title']} at {organization}")
    else:
        lines.append("(unmatched to a specific applied opportunity)")
    if preview:
        lines.append(f"\n{preview}")
    return "\n".join(lines)


def check_mail(
    database: Database, constitution: Constitution, settings: Settings
) -> list[dict[str, Any]]:
    """Check for new mail. Returns one dict per detected message:
    `text` (the alert to send), `subject`, `body` (preview), and
    `opportunity_id` (the best-effort match, or None) - everything a
    caller needs to both send a Telegram alert and record a
    Notification row. Never raises: auth/network failures are logged
    and produce an empty list for this cycle rather than crashing the
    listener.
    """
    if not settings.ms_graph_client_id:
        return []

    try:
        access_token = get_access_token(settings)
        if access_token is None:
            logger.warning("Graph auth unavailable this cycle; skipping mail check.")
            return []
        messages = fetch_new_messages(access_token, settings.graph_delta_link_path)
    except httpx.HTTPError as exc:
        logger.warning("Graph mail check failed: %s", exc)
        return []

    if not messages:
        return []

    applied_opportunities = OpportunityService(database, constitution).list_opportunities(
        lifecycle_status="applied"
    )

    alerts = []
    for message in messages:
        opportunity_id = correlate_opportunity(message, applied_opportunities)
        matched = next(
            (o for o in applied_opportunities if o["id"] == opportunity_id), None
        )
        alerts.append(
            {
                "text": format_mail_alert(message, matched),
                "subject": message.get("subject") or "(no subject)",
                "body": message.get("bodyPreview") or "",
                "opportunity_id": opportunity_id,
            }
        )
    return alerts
