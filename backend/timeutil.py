"""Timestamp formatting shared across services and adapters."""

from datetime import datetime, timezone


def now_iso() -> str:
    """Match schema.sql's `strftime('%Y-%m-%dT%H:%M:%fZ', 'now')` format."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond:06d}Z"
