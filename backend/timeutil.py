"""Timestamp formatting shared across services and adapters."""

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime


def now_iso() -> str:
    """Match schema.sql's `strftime('%Y-%m-%dT%H:%M:%fZ', 'now')` format."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond:06d}Z"


def add_days_iso(days: int) -> str:
    """now() + N days, in our ISO format (e.g. for `opportunities.remind_at`)."""
    return _to_iso(datetime.now(timezone.utc) + timedelta(days=days))


def _to_iso(moment: datetime) -> str:
    moment = moment.astimezone(timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond:06d}Z"


def parse_rfc822(value: str | None) -> str | None:
    """Parse an RFC 822/2822 date (e.g. RSS `<pubDate>`/`<expires_at>`) to our ISO format."""
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return _to_iso(parsed)


def from_unix_timestamp(value: int | float | None) -> str | None:
    """Convert a Unix timestamp (e.g. Himalayas' `expiryDate`) to our ISO format."""
    if value is None:
        return None
    try:
        parsed = datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None
    return _to_iso(parsed)
