"""Tests for applied-response status tracking (OE-ADR-041)."""

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


def test_set_response_status_writes_value_and_audits(tmp_path: Path) -> None:
    service, database = _service(tmp_path)
    opportunity_id, _ = service.create_manual(_opportunity())
    service.mark_applied(opportunity_id)

    service.set_response_status(opportunity_id, "interview")

    opportunity = service.get_opportunity(opportunity_id)
    assert opportunity["response_status"] == "interview"
    with database.session() as session:
        audit_events = (
            session.execute(
                select(AuditEventRecord).where(
                    AuditEventRecord.event_type == "opportunity_response_status_changed"
                )
            )
            .scalars()
            .all()
        )
    assert len(audit_events) == 1
    assert audit_events[0].entity_id == opportunity_id


def test_set_response_status_rejects_invalid_value(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    opportunity_id, _ = service.create_manual(_opportunity())

    with pytest.raises(ValueError):
        service.set_response_status(opportunity_id, "not_a_real_status")


def test_set_response_status_none_clears_it(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    opportunity_id, _ = service.create_manual(_opportunity())
    service.set_response_status(opportunity_id, "responded")

    service.set_response_status(opportunity_id, None)

    opportunity = service.get_opportunity(opportunity_id)
    assert opportunity["response_status"] is None


def test_set_response_status_overwrites_on_resetting(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    opportunity_id, _ = service.create_manual(_opportunity())
    service.set_response_status(opportunity_id, "responded")

    service.set_response_status(opportunity_id, "interview")

    opportunity = service.get_opportunity(opportunity_id)
    assert opportunity["response_status"] == "interview"


def test_set_response_status_never_changes_lifecycle_status_or_applied_at(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    opportunity_id, _ = service.create_manual(_opportunity())
    service.record_review_decision(opportunity_id, "shortlist")
    service.mark_applied(opportunity_id)

    service.set_response_status(opportunity_id, "offer")

    opportunity = service.get_opportunity(opportunity_id)
    assert opportunity["lifecycle_status"] == "shortlisted"
    assert opportunity["applied_at"] is not None
    assert opportunity["response_status"] == "offer"


def test_list_opportunities_response_status_filter(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    interview_id, _ = service.create_manual(
        _opportunity(title="Interview Stage", source_url="https://example.com/jobs/2")
    )
    service.set_response_status(interview_id, "interview")

    declined_id, _ = service.create_manual(
        _opportunity(title="Declined", source_url="https://example.com/jobs/3")
    )
    service.set_response_status(declined_id, "declined")

    no_response_id, _ = service.create_manual(
        _opportunity(title="No Response", source_url="https://example.com/jobs/4")
    )

    interview_rows = service.list_opportunities(lifecycle_status="interview")
    assert {row["id"] for row in interview_rows} == {interview_id}

    declined_rows = service.list_opportunities(lifecycle_status="declined")
    assert {row["id"] for row in declined_rows} == {declined_id}
    assert no_response_id not in {row["id"] for row in declined_rows}


def test_response_status_does_not_collide_with_lifecycle_rejected(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    lifecycle_rejected_id, _ = service.create_manual(
        _opportunity(title="Lifecycle Rejected", source_url="https://example.com/jobs/5")
    )
    service.record_review_decision(lifecycle_rejected_id, "reject")

    response_declined_id, _ = service.create_manual(
        _opportunity(title="Response Declined", source_url="https://example.com/jobs/6")
    )
    service.set_response_status(response_declined_id, "declined")

    lifecycle_rejected_rows = service.list_opportunities(lifecycle_status="rejected")
    assert {row["id"] for row in lifecycle_rejected_rows} == {lifecycle_rejected_id}

    declined_rows = service.list_opportunities(lifecycle_status="declined")
    assert {row["id"] for row in declined_rows} == {response_declined_id}


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


def test_response_status_route_sets_and_clears(client: TestClient) -> None:
    created = client.post("/opportunities", data=_form(), follow_redirects=False)
    detail_path = urlparse(created.headers["location"]).path
    client.post(f"{detail_path}/apply", data={}, follow_redirects=False)

    response = client.post(
        f"{detail_path}/response-status", data={"status": "offer"}, follow_redirects=False
    )
    assert response.status_code == 303

    detail = client.get(detail_path)
    assert "Offer" in detail.text

    clear = client.post(
        f"{detail_path}/response-status", data={"status": ""}, follow_redirects=False
    )
    assert clear.status_code == 303


def test_response_status_route_rejects_invalid_value(client: TestClient) -> None:
    created = client.post("/opportunities", data=_form(), follow_redirects=False)
    detail_path = urlparse(created.headers["location"]).path

    response = client.post(
        f"{detail_path}/response-status",
        data={"status": "not_a_real_status"},
        follow_redirects=False,
    )
    assert response.status_code == 422


def test_response_status_route_404s_for_missing_opportunity(client: TestClient) -> None:
    response = client.post(
        "/opportunities/999999/response-status", data={"status": "interview"}
    )
    assert response.status_code == 404


def test_dashboard_response_status_filter_and_badge(client: TestClient) -> None:
    created = client.post("/opportunities", data=_form(), follow_redirects=False)
    detail_path = urlparse(created.headers["location"]).path
    client.post(f"{detail_path}/apply", data={}, follow_redirects=False)
    client.post(f"{detail_path}/response-status", data={"status": "interview"}, follow_redirects=False)

    dashboard = client.get("/")
    assert "Interview" in dashboard.text

    filtered = client.get("/?status=interview")
    assert "Cloud Administrator" in filtered.text
