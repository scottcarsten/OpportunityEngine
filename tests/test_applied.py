"""Tests for tracking applied opportunities (OE-ADR-034)."""

from pathlib import Path
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app import create_app
from backend.config import Settings
from backend.database import Database
from backend.db.models import AuditEventRecord
from backend.models import OpportunityInput
from backend.services.constitution_service import load_constitution
from backend.services.opportunity_service import OpportunityService


def _service(tmp_path: Path) -> tuple[OpportunityService, Database]:
    database = Database(database_path=tmp_path / "opportunity_engine.db")
    database.initialize()
    constitution = load_constitution(Path("config/constitution.json"))
    return OpportunityService(database, constitution), database


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


def test_mark_applied_defaults_to_now(tmp_path: Path) -> None:
    service, database = _service(tmp_path)
    opportunity_id, _ = service.create_manual(_opportunity())

    service.mark_applied(opportunity_id)

    opportunity = service.get_opportunity(opportunity_id)
    assert opportunity["applied_at"] is not None

    with database.session() as session:
        audit_events = session.execute(
            select(AuditEventRecord).where(AuditEventRecord.event_type == "opportunity_applied")
        ).scalars().all()
    assert len(audit_events) == 1
    assert audit_events[0].entity_id == opportunity_id


def test_mark_applied_with_explicit_date(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    opportunity_id, _ = service.create_manual(_opportunity())

    service.mark_applied(opportunity_id, applied_at="2026-08-01T00:00:00.000000Z")

    opportunity = service.get_opportunity(opportunity_id)
    assert opportunity["applied_at"] == "2026-08-01T00:00:00.000000Z"


def test_mark_applied_never_changes_lifecycle_status(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    opportunity_id, _ = service.create_manual(_opportunity())
    service.record_review_decision(opportunity_id, "shortlist")

    service.mark_applied(opportunity_id)

    opportunity = service.get_opportunity(opportunity_id)
    assert opportunity["lifecycle_status"] == "shortlisted"
    assert opportunity["applied_at"] is not None


def test_unmark_applied_clears_the_date_and_audits(tmp_path: Path) -> None:
    service, database = _service(tmp_path)
    opportunity_id, _ = service.create_manual(_opportunity())
    service.mark_applied(opportunity_id)

    service.unmark_applied(opportunity_id)

    opportunity = service.get_opportunity(opportunity_id)
    assert opportunity["applied_at"] is None
    with database.session() as session:
        audit_events = session.execute(
            select(AuditEventRecord).where(
                AuditEventRecord.event_type == "opportunity_applied_undone"
            )
        ).scalars().all()
    assert len(audit_events) == 1


def test_list_opportunities_applied_filter_is_independent_of_status(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    shortlisted_applied_id, _ = service.create_manual(
        _opportunity(title="Shortlisted And Applied", source_url="https://example.com/jobs/2")
    )
    service.record_review_decision(shortlisted_applied_id, "shortlist")
    service.mark_applied(shortlisted_applied_id)

    preparing_applied_id, _ = service.create_manual(
        _opportunity(title="Preparing And Applied", source_url="https://example.com/jobs/3")
    )
    service.record_review_decision(preparing_applied_id, "request_preparation")
    service.mark_applied(preparing_applied_id)

    not_applied_id, _ = service.create_manual(
        _opportunity(title="Not Applied", source_url="https://example.com/jobs/4")
    )

    applied = service.list_opportunities(lifecycle_status="applied")
    applied_ids = {row["id"] for row in applied}

    assert applied_ids == {shortlisted_applied_id, preparing_applied_id}
    assert not_applied_id not in applied_ids
    statuses = {row["id"]: row["lifecycle_status"] for row in applied}
    assert statuses[shortlisted_applied_id] == "shortlisted"
    assert statuses[preparing_applied_id] == "preparing"


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


def test_apply_route_with_no_date_defaults_to_now(client: TestClient) -> None:
    created = client.post("/opportunities", data=_form(), follow_redirects=False)
    detail_path = urlparse(created.headers["location"]).path

    response = client.post(f"{detail_path}/apply", data={}, follow_redirects=False)
    assert response.status_code == 303

    detail = client.get(detail_path)
    assert "Applied" in detail.text
    assert "Unmark applied" in detail.text


def test_apply_route_with_explicit_date(client: TestClient) -> None:
    created = client.post("/opportunities", data=_form(), follow_redirects=False)
    detail_path = urlparse(created.headers["location"]).path

    response = client.post(
        f"{detail_path}/apply", data={"applied_date": "2026-08-01"}, follow_redirects=False
    )
    assert response.status_code == 303

    detail = client.get(detail_path)
    assert "2026-08-01" in detail.text


def test_apply_route_rejects_invalid_date(client: TestClient) -> None:
    created = client.post("/opportunities", data=_form(), follow_redirects=False)
    detail_path = urlparse(created.headers["location"]).path

    response = client.post(
        f"{detail_path}/apply", data={"applied_date": "not-a-date"}, follow_redirects=False
    )
    assert response.status_code == 422


def test_unapply_route_clears_applied_state(client: TestClient) -> None:
    created = client.post("/opportunities", data=_form(), follow_redirects=False)
    detail_path = urlparse(created.headers["location"]).path
    client.post(f"{detail_path}/apply", data={}, follow_redirects=False)

    response = client.post(f"{detail_path}/unapply", data={}, follow_redirects=False)
    assert response.status_code == 303

    detail = client.get(detail_path)
    assert "Mark applied" in detail.text
    assert "Unmark applied" not in detail.text


def test_dashboard_applied_filter_and_badge(client: TestClient) -> None:
    created = client.post("/opportunities", data=_form(), follow_redirects=False)
    detail_path = urlparse(created.headers["location"]).path

    applied_filter_before = client.get("/?status=applied")
    assert "No opportunities match these filters" in applied_filter_before.text

    client.post(f"{detail_path}/apply", data={}, follow_redirects=False)

    dashboard = client.get("/")
    assert "Applied" in dashboard.text

    applied_filter_after = client.get("/?status=applied")
    assert "Cloud Administrator" in applied_filter_after.text
