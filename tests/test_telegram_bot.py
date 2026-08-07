"""Tests for the Telegram command listener (OE-ADR-035)."""

from pathlib import Path

import pytest

from backend.adapters.base import RawOpportunityRecord
from backend.database import Database
from backend.models import OpportunityInput
from backend.services.constitution_service import load_constitution
from backend.services.opportunity_service import OpportunityService
from backend.telegram_bot import dispatch_command, handle_update

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
