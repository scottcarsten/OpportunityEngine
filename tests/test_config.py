"""Configuration safety tests."""

import pytest
from pydantic import ValidationError

from backend.config import Settings


def test_default_host_is_loopback() -> None:
    settings = Settings()
    assert settings.host == "127.0.0.1"


def test_non_loopback_host_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(host="0.0.0.0")

