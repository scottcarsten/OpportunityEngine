"""Tests for the Telegram push-notification channel (OE-ADR-035)."""

from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from backend.config import Settings
from backend.database import Database
from backend.db.models import Notification
from backend.models import OpportunityInput
from backend.notifications import send_telegram
from backend.services.constitution_service import load_constitution
from backend.services.opportunity_service import OpportunityService


def _opportunity(**overrides: object) -> OpportunityInput:
    values: dict[str, object] = {
        "title": "Cloud Administrator",
        "organization_name": "Acme Corp",
        "description": "Manage Azure and AWS environments for our engineering team.",
        "source_url": "https://example.com/jobs/1",
        "location_text": "United States",
        "remote_status": "remote",
        "engagement_type": "contract",
        "tax_type": "1099",
        "schedule_text": "After hours",
        "compensation_min": None,
        "compensation_max": None,
        "compensation_period": None,
        "requires_travel": False,
        "requires_relocation": False,
        "requires_clearance": False,
        "replaces_full_time_work": False,
    }
    values.update(overrides)
    return OpportunityInput(**values)


def _service(tmp_path: Path, *, telegram_bot_token: str | None) -> OpportunityService:
    database = Database(database_path=tmp_path / "opportunity_engine.db")
    database.initialize()
    constitution = load_constitution(Path("config/constitution.json"))
    settings = Settings(telegram_bot_token=telegram_bot_token, telegram_chat_id="12345")
    return OpportunityService(database, constitution, settings)


def test_send_telegram_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.telegram.org/bot123:abc/sendMessage"
        return httpx.Response(200)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    sent, error = send_telegram("123:abc", "12345", "Hello", client=client)

    assert sent is True
    assert error is None


def test_send_telegram_http_error_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    sent, error = send_telegram("123:abc", "12345", "Hello", client=client)

    assert sent is False
    assert error is not None


def test_send_telegram_connection_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    sent, error = send_telegram("123:abc", "12345", "Hello", client=client)

    assert sent is False
    assert "connection refused" in error


def test_ingest_without_telegram_token_creates_only_dashboard_notification(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path, telegram_bot_token=None)
    opportunity_id, _ = service.create_manual(_opportunity())

    with service.database.session() as session:
        notifications = session.execute(
            select(Notification).where(Notification.opportunity_id == opportunity_id)
        ).scalars().all()

    assert [n.channel for n in notifications] == ["dashboard"]


def test_ingest_with_telegram_configured_sends_and_records_both_channels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, str, str]] = []

    def fake_send_telegram(bot_token: str, chat_id: str, text: str) -> tuple[bool, str | None]:
        calls.append((bot_token, chat_id, text))
        return True, None

    monkeypatch.setattr(
        "backend.services.opportunity_service.send_telegram", fake_send_telegram
    )

    service = _service(tmp_path, telegram_bot_token="123:abc")
    opportunity_id, _ = service.create_manual(_opportunity())

    with service.database.session() as session:
        notifications = session.execute(
            select(Notification).where(Notification.opportunity_id == opportunity_id)
        ).scalars().all()

    channels = {n.channel: n for n in notifications}
    assert set(channels) == {"dashboard", "telegram"}
    assert channels["telegram"].status == "sent"
    assert channels["telegram"].sent_at is not None
    assert channels["telegram"].is_external == 0
    assert len(calls) == 1
    assert calls[0][0] == "123:abc"
    assert calls[0][1] == "12345"


def test_ingest_records_failed_telegram_delivery_without_blocking_ingest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_send_telegram(bot_token: str, chat_id: str, text: str) -> tuple[bool, str | None]:
        return False, "boom"

    monkeypatch.setattr(
        "backend.services.opportunity_service.send_telegram", fake_send_telegram
    )

    service = _service(tmp_path, telegram_bot_token="123:abc")
    opportunity_id, created = service.create_manual(_opportunity())

    assert created is True
    with service.database.session() as session:
        notifications = session.execute(
            select(Notification).where(Notification.opportunity_id == opportunity_id)
        ).scalars().all()

    channels = {n.channel: n for n in notifications}
    assert channels["telegram"].status == "failed"
    assert channels["telegram"].error_summary == "boom"
    assert channels["telegram"].sent_at is None
