"""Structured logging without secret or document payloads."""

import json
import logging
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any


class JsonFormatter(logging.Formatter):
    """Format application log records as single-line JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        correlation_id = getattr(record, "correlation_id", None)
        if correlation_id:
            payload["correlation_id"] = correlation_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str, log_file: Path | None = None) -> None:
    """Configure structured root handlers: always stdout, optionally a
    rolling file too - for unattended processes like the Telegram
    listener, where nobody's watching a terminal to catch stdout.

    `log_file` rotates daily and keeps 7 days of history; older files
    are deleted automatically, so this never grows unbounded.

    Also re-enables every already-created logger. Alembic's migration
    runner calls `logging.config.fileConfig()` on `alembic.ini`
    (`database/migrations/env.py`), and `fileConfig`'s default
    `disable_existing_loggers=True` silently disables every logger that
    already existed at that point - including one any caller's own
    module created at import time (e.g. `logging.getLogger(__name__)`
    at the top of `backend/telegram_bot.py`). A disabled logger drops
    every record with no error, so this function - the one place
    meant to leave logging in a known-good state - has to undo that.
    """
    formatter = JsonFormatter()
    root = logging.getLogger()
    root.handlers.clear()
    for logger_name in list(root.manager.loggerDict):
        logging.getLogger(logger_name).disabled = False

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = TimedRotatingFileHandler(
            log_file, when="midnight", backupCount=7, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    root.setLevel(level)

