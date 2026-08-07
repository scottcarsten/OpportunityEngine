"""Tests for structured logging, including the rolling file handler."""

import json
import logging
from pathlib import Path

from backend.logging_config import configure_logging


def test_configure_logging_without_file_only_adds_stream_handler() -> None:
    configure_logging("INFO")

    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0], logging.StreamHandler)


def test_configure_logging_with_file_writes_json_lines(tmp_path: Path) -> None:
    log_file = tmp_path / "logs" / "telegram_bot.log"
    configure_logging("INFO", log_file=log_file)

    logging.getLogger("test").info("hello from the listener")
    for handler in logging.getLogger().handlers:
        handler.flush()

    assert log_file.exists()
    lines = log_file.read_text().strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["message"] == "hello from the listener"
    assert payload["level"] == "INFO"
