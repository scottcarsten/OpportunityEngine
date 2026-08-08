"""Tests for the Telegram command listener (OE-ADR-035)."""

from pathlib import Path

import pytest

from backend.adapters.base import RawOpportunityRecord
from backend.config import Settings
from backend.database import Database
from backend.db.models import Notification
from backend.graph_mail import GraphAuthExpiredError
from backend.models import OpportunityInput
from backend.services.constitution_service import load_constitution
from backend.services.opportunity_service import OpportunityService
from backend.telegram_bot import (
    dispatch_command,
    handle_update,
    run_mail_check,
    run_periodic_collection,
)

_CHAT_ID = "12345"


class FakeAdapter:
    source_name = "Fake Source"
    source_type = "fake"
    base_url = "https://example.com/fake-feed"

    def fetch(self) -> list[RawOpportunityRecord]:
        return [
            RawOpportunityRecord(
                external_id="job-1",
                canonical_url="https://example.com/jobs/1",
                retrieved_at="2026-08-05T00:00:00.000000Z",
                raw_payload={"title": "Fake Co: Systems Administrator"},
            )
        ]

    def normalize(self, record: RawOpportunityRecord) -> OpportunityInput:
        title = record.raw_payload["title"]
        organization_name, _, job_title = title.partition(": ")
        return OpportunityInput(
            title=job_title,
            organization_name=organization_name,
            description=f"Description for {job_title}.",
            source_url=record.canonical_url,
            location_text="Anywhere",
            remote_status="remote",
            engagement_type="contract",
            tax_type="unknown",
            schedule_text="",
            compensation_min=None,
            compensation_max=None,
            compensation_period=None,
            requires_travel=None,
            requires_relocation=None,
            requires_clearance=None,
            replaces_full_time_work=None,
        )


class FailingAdapter:
    source_name = "Failing Source"
    source_type = "fake"
    base_url = "https://example.com/failing-feed"

    def fetch(self) -> list[RawOpportunityRecord]:
        raise RuntimeError("feed unreachable")

    def normalize(self, record: RawOpportunityRecord) -> OpportunityInput:
        raise AssertionError("should never be called")


def _setup(tmp_path: Path):
    database = Database(database_path=tmp_path / "opportunity_engine.db")
    database.initialize()
    constitution = load_constitution(Path("config/constitution.json"))
    return database, constitution


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


def test_status_command_reports_real_counts(tmp_path: Path) -> None:
    database, constitution = _setup(tmp_path)
    OpportunityService(database, constitution).create_manual(_opportunity())

    reply = dispatch_command("/status", database, constitution, "123:abc", _CHAT_ID)

    assert "1 pending review (new/eligible)" in reply


def test_pending_command_lists_new_and_eligible(tmp_path: Path) -> None:
    database, constitution = _setup(tmp_path)
    service = OpportunityService(database, constitution)
    service.create_manual(_opportunity(title="Eligible Role"))
    service.create_manual(
        _opportunity(
            title="Ineligible Role", source_url="https://example.com/jobs/2", requires_travel=True
        )
    )

    reply = dispatch_command("/pending", database, constitution, "123:abc", _CHAT_ID)

    assert "Eligible Role" in reply
    assert "Ineligible Role" not in reply


def test_pending_command_empty_state(tmp_path: Path) -> None:
    database, constitution = _setup(tmp_path)

    reply = dispatch_command("/pending", database, constitution, "123:abc", _CHAT_ID)

    assert "Nothing pending" in reply


def test_new_command_excludes_eligible(tmp_path: Path) -> None:
    database, constitution = _setup(tmp_path)
    service = OpportunityService(database, constitution)
    service.create_manual(_opportunity(title="Clean Eligible Role"))
    service.create_manual(
        _opportunity(
            title="Ambiguous Role", source_url="https://example.com/jobs/2", requires_clearance=None
        )
    )

    reply = dispatch_command("/new", database, constitution, "123:abc", _CHAT_ID)

    assert "Ambiguous Role" in reply
    assert "Clean Eligible Role" not in reply


def test_newsearch_runs_collection_and_reports_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database, constitution = _setup(tmp_path)
    monkeypatch.setattr("backend.telegram_bot.ADAPTERS", {"fake_source": FakeAdapter})
    sent: list[str] = []
    monkeypatch.setattr(
        "backend.telegram_bot.send_telegram",
        lambda token, chat_id, text: (sent.append(text), (True, None))[1],
    )

    reply = dispatch_command("/newsearch", database, constitution, "123:abc", _CHAT_ID)

    assert "Collection complete" in reply
    assert "fake_source" in reply
    assert any("Starting collection" in text for text in sent)


def test_run_periodic_collection_stays_silent_on_a_clean_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database, constitution = _setup(tmp_path)
    monkeypatch.setattr("backend.telegram_bot.ADAPTERS", {"fake_source": FakeAdapter})

    alert = run_periodic_collection(database, constitution)

    assert alert is None


def test_run_periodic_collection_alerts_on_a_failed_adapter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database, constitution = _setup(tmp_path)
    monkeypatch.setattr("backend.telegram_bot.ADAPTERS", {"failing_source": FailingAdapter})

    alert = run_periodic_collection(database, constitution)

    assert alert is not None
    assert "failing_source" in alert
    assert "failed" in alert


def test_run_mail_check_sends_alert_and_records_notification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database, constitution = _setup(tmp_path)
    settings = Settings(telegram_bot_token="123:abc", telegram_chat_id=_CHAT_ID)
    sent: list[str] = []

    monkeypatch.setattr(
        "backend.telegram_bot.check_mail",
        lambda db, const, s: [
            {
                "text": "New email from Jane",
                "subject": "Re: application",
                "body": "preview",
                "opportunity_id": None,
            }
        ],
    )
    monkeypatch.setattr(
        "backend.telegram_bot.send_telegram",
        lambda token, chat_id, text: (sent.append(text), (True, None))[1],
    )

    run_mail_check(database, constitution, settings)

    assert sent == ["New email from Jane"]
    with database.session() as session:
        notifications = session.query(Notification).filter_by(
            notification_type="employer_reply"
        ).all()
    assert len(notifications) == 1
    assert notifications[0].status == "sent"


def test_run_mail_check_auto_sets_responded_on_match_when_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database, constitution = _setup(tmp_path)
    service = OpportunityService(database, constitution)
    opportunity_id, _ = service.create_manual(_opportunity())
    service.mark_applied(opportunity_id)
    settings = Settings(telegram_bot_token="123:abc", telegram_chat_id=_CHAT_ID)

    monkeypatch.setattr(
        "backend.telegram_bot.check_mail",
        lambda db, const, s: [
            {
                "text": "New email from Jane",
                "subject": "Re: application",
                "body": "preview",
                "opportunity_id": opportunity_id,
            }
        ],
    )
    monkeypatch.setattr(
        "backend.telegram_bot.send_telegram", lambda token, chat_id, text: (True, None)
    )

    run_mail_check(database, constitution, settings)

    opportunity = service.get_opportunity(opportunity_id)
    assert opportunity["response_status"] == "responded"


def test_run_mail_check_never_overwrites_a_more_specific_response_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database, constitution = _setup(tmp_path)
    service = OpportunityService(database, constitution)
    opportunity_id, _ = service.create_manual(_opportunity())
    service.mark_applied(opportunity_id)
    service.set_response_status(opportunity_id, "interview")
    settings = Settings(telegram_bot_token="123:abc", telegram_chat_id=_CHAT_ID)

    monkeypatch.setattr(
        "backend.telegram_bot.check_mail",
        lambda db, const, s: [
            {
                "text": "New email from Jane",
                "subject": "Re: application",
                "body": "preview",
                "opportunity_id": opportunity_id,
            }
        ],
    )
    monkeypatch.setattr(
        "backend.telegram_bot.send_telegram", lambda token, chat_id, text: (True, None)
    )

    run_mail_check(database, constitution, settings)

    opportunity = service.get_opportunity(opportunity_id)
    assert opportunity["response_status"] == "interview"


def test_run_mail_check_alerts_on_graph_auth_expired(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database, constitution = _setup(tmp_path)
    settings = Settings(telegram_bot_token="123:abc", telegram_chat_id=_CHAT_ID)
    sent: list[str] = []

    def _raise(db: object, const: object, s: object) -> list:
        raise GraphAuthExpiredError()

    monkeypatch.setattr("backend.telegram_bot.check_mail", _raise)
    monkeypatch.setattr(
        "backend.telegram_bot.send_telegram",
        lambda token, chat_id, text: (sent.append(text), (True, None))[1],
    )

    run_mail_check(database, constitution, settings)

    assert len(sent) == 1
    assert "python -m backend.graph_mail" in sent[0]


def test_run_mail_check_alerts_on_unexpected_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database, constitution = _setup(tmp_path)
    settings = Settings(telegram_bot_token="123:abc", telegram_chat_id=_CHAT_ID)
    sent: list[str] = []

    def _raise(db: object, const: object, s: object) -> list:
        raise RuntimeError("network blip")

    monkeypatch.setattr("backend.telegram_bot.check_mail", _raise)
    monkeypatch.setattr(
        "backend.telegram_bot.send_telegram",
        lambda token, chat_id, text: (sent.append(text), (True, None))[1],
    )

    run_mail_check(database, constitution, settings)

    assert len(sent) == 1
    assert "Mail check failed" in sent[0]
    assert "network blip" in sent[0]


def test_unknown_command_returns_usage(tmp_path: Path) -> None:
    database, constitution = _setup(tmp_path)

    reply = dispatch_command("/bogus", database, constitution, "123:abc", _CHAT_ID)

    assert "Unknown command" in reply


def test_handle_update_ignores_other_chats(tmp_path: Path) -> None:
    database, constitution = _setup(tmp_path)
    update = {
        "message": {
            "chat": {"id": 99999},
            "text": "/status",
        }
    }

    reply, chat_id = handle_update(update, _CHAT_ID, database, constitution, "123:abc")

    assert reply is None
    assert chat_id is None


def test_handle_update_ignores_non_command_text(tmp_path: Path) -> None:
    database, constitution = _setup(tmp_path)
    update = {
        "message": {
            "chat": {"id": int(_CHAT_ID)},
            "text": "just chatting, not a command",
        }
    }

    reply, chat_id = handle_update(update, _CHAT_ID, database, constitution, "123:abc")

    assert reply is None
    assert chat_id is None


def test_handle_update_dispatches_recognized_command(tmp_path: Path) -> None:
    database, constitution = _setup(tmp_path)
    update = {
        "message": {
            "chat": {"id": int(_CHAT_ID)},
            "text": "/status",
        }
    }

    reply, chat_id = handle_update(update, _CHAT_ID, database, constitution, "123:abc")

    assert reply is not None
    assert "pending review" in reply
    assert chat_id == _CHAT_ID


def test_handle_update_ignores_updates_with_no_message(tmp_path: Path) -> None:
    database, constitution = _setup(tmp_path)

    reply, chat_id = handle_update({}, _CHAT_ID, database, constitution, "123:abc")

    assert reply is None
    assert chat_id is None
