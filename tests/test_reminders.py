"""Tests for follow-up reminders on deferred opportunities (OE-ADR-030)."""

from pathlib import Path
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from backend.app import create_app
from backend.config import Settings
from backend.database import Database
from backend.db.models import AuditEventRecord, Notification, Opportunity
from backend.models import OpportunityInput
from backend.services.constitution_service import load_constitution
from backend.services.opportunity_service import OpportunityService


def _service(
    tmp_path: Path, *, telegram_bot_token: str | None = None
) -> tuple[OpportunityService, Database]:
    database = Database(database_path=tmp_path / "opportunity_engine.db")
    database.initialize()
    constitution = load_constitution(Path("config/constitution.json"))
    settings = Settings(telegram_bot_token=telegram_bot_token, telegram_chat_id="12345")
    return OpportunityService(database, constitution, settings), database


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


def test_defer_with_remind_days_sets_remind_at(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    opportunity_id, _ = service.create_manual(_opportunity())

    service.record_review_decision(opportunity_id, "defer", remind_days=3)

    opportunity = service.get_opportunity(opportunity_id)
    assert opportunity["lifecycle_status"] == "deferred"
    assert opportunity["remind_at"] is not None


def test_defer_without_remind_days_leaves_remind_at_none(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    opportunity_id, _ = service.create_manual(_opportunity())

    service.record_review_decision(opportunity_id, "defer")

    opportunity = service.get_opportunity(opportunity_id)
    assert opportunity["remind_at"] is None


def test_later_decision_clears_a_pending_reminder(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    opportunity_id, _ = service.create_manual(_opportunity())

    service.record_review_decision(opportunity_id, "defer", remind_days=7)
    assert service.get_opportunity(opportunity_id)["remind_at"] is not None

    service.record_review_decision(opportunity_id, "shortlist")

    assert service.get_opportunity(opportunity_id)["remind_at"] is None


def test_surface_due_reminders_notifies_and_clears_remind_at(tmp_path: Path) -> None:
    service, database = _service(tmp_path)
    opportunity_id, _ = service.create_manual(_opportunity())
    service.record_review_decision(opportunity_id, "defer", remind_days=7)

    with database.session() as session:
        session.execute(
            update(Opportunity)
            .where(Opportunity.id == opportunity_id)
            .values(remind_at="2000-01-01T00:00:00.000000Z")
        )
        session.commit()

    due_ids = service.surface_due_reminders()

    assert opportunity_id in due_ids
    opportunity = service.get_opportunity(opportunity_id)
    assert opportunity["remind_at"] is None
    assert opportunity["lifecycle_status"] == "deferred"

    with database.session() as session:
        notifications = session.execute(
            select(Notification).where(
                Notification.opportunity_id == opportunity_id,
                Notification.notification_type == "follow_up_reminder",
            )
        ).scalars().all()
        audit_events = session.execute(
            select(AuditEventRecord).where(
                AuditEventRecord.event_type == "follow_up_reminder_surfaced"
            )
        ).scalars().all()
    assert [n.channel for n in notifications] == ["dashboard"]
    assert len(audit_events) == 1
    assert audit_events[0].entity_id == opportunity_id


def test_surface_due_reminders_leaves_a_future_reminder_alone(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    opportunity_id, _ = service.create_manual(_opportunity())
    service.record_review_decision(opportunity_id, "defer", remind_days=7)

    due_ids = service.surface_due_reminders()

    assert opportunity_id not in due_ids
    assert service.get_opportunity(opportunity_id)["remind_at"] is not None


def test_surface_due_reminders_ignores_non_deferred_opportunities(tmp_path: Path) -> None:
    service, database = _service(tmp_path)
    opportunity_id, _ = service.create_manual(_opportunity())
    service.record_review_decision(opportunity_id, "shortlist")

    with database.session() as session:
        session.execute(
            update(Opportunity)
            .where(Opportunity.id == opportunity_id)
            .values(remind_at="2000-01-01T00:00:00.000000Z")
        )
        session.commit()

    due_ids = service.surface_due_reminders()

    assert due_ids == []


def test_surface_due_reminders_sends_telegram_when_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def fake_send_telegram(bot_token: str, chat_id: str, text: str) -> tuple[bool, str | None]:
        calls.append(text)
        return True, None

    monkeypatch.setattr(
        "backend.services.opportunity_service.send_telegram", fake_send_telegram
    )

    service, database = _service(tmp_path, telegram_bot_token="123:abc")
    opportunity_id, _ = service.create_manual(_opportunity())
    service.record_review_decision(opportunity_id, "defer", remind_days=7)
    with database.session() as session:
        session.execute(
            update(Opportunity)
            .where(Opportunity.id == opportunity_id)
            .values(remind_at="2000-01-01T00:00:00.000000Z")
        )
        session.commit()

    service.surface_due_reminders()

    with database.session() as session:
        notifications = session.execute(
            select(Notification).where(
                Notification.opportunity_id == opportunity_id,
                Notification.notification_type == "follow_up_reminder",
            )
        ).scalars().all()
    assert {n.channel for n in notifications} == {"dashboard", "telegram"}
    # One telegram call from ingest (eligible opportunity) plus one from the
    # reminder sweep - assert the reminder's own call happened.
    assert any(text.startswith("Follow-up:") for text in calls)


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = Settings(
        database_path=tmp_path / "opportunity_engine.db",
        constitution_path=Path("config/constitution.json"),
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _form(**overrides: str) -> dict[str, str]:
    values = {
        "title": "Cloud Administrator",
        "organization_name": "Acme Corp",
        "description": "Manage Azure and AWS environments for our engineering team.",
        "source_url": "https://example.com/jobs/1",
        "location_text": "United States",
        "remote_status": "remote",
        "engagement_type": "contract",
        "tax_type": "1099",
        "schedule_text": "After hours",
        "compensation_min": "",
        "compensation_max": "",
        "compensation_period": "unknown",
        "requires_travel": "no",
        "requires_relocation": "no",
        "requires_clearance": "no",
        "replaces_full_time_work": "no",
    }
    values.update(overrides)
    return values


def test_review_route_defer_quick_pick_sets_remind_at(client: TestClient) -> None:
    created = client.post("/opportunities", data=_form(), follow_redirects=False)
    detail_path = urlparse(created.headers["location"]).path

    response = client.post(
        f"{detail_path}/review", data={"defer_remind_days": "7"}, follow_redirects=False
    )
    assert response.status_code == 303

    detail = client.get(detail_path)
    assert "Deferred" in detail.text
    assert "Reminds you" in detail.text


def test_review_route_defer_no_reminder_omits_reminder(client: TestClient) -> None:
    created = client.post("/opportunities", data=_form(), follow_redirects=False)
    detail_path = urlparse(created.headers["location"]).path

    response = client.post(
        f"{detail_path}/review", data={"defer_remind_days": ""}, follow_redirects=False
    )
    assert response.status_code == 303

    detail = client.get(detail_path)
    assert "Deferred" in detail.text
    assert "Reminds you" not in detail.text


def test_dashboard_follow_up_due_filter(client: TestClient) -> None:
    created = client.post("/opportunities", data=_form(), follow_redirects=False)
    detail_path = urlparse(created.headers["location"]).path
    opportunity_id = int(detail_path.rsplit("/", 1)[-1])

    client.post(f"{detail_path}/review", data={"defer_remind_days": "7"}, follow_redirects=False)

    due_filter_before = client.get("/?status=follow_up_due")
    assert "No opportunities match these filters" in due_filter_before.text

    with client.app.state.database.session() as session:
        session.execute(
            update(Opportunity)
            .where(Opportunity.id == opportunity_id)
            .values(remind_at="2000-01-01T00:00:00.000000Z")
        )
        session.commit()

    due_filter_after = client.get("/?status=follow_up_due")
    assert "Cloud Administrator" in due_filter_after.text
