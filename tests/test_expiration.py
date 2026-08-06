"""Tests for opportunity aging/last_seen_at tracking and stale-listing expiration."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from backend.app import create_app
from backend.config import Settings
from backend.database import Database
from backend.db.models import AuditEventRecord, Opportunity
from backend.models import OpportunityInput
from backend.services.constitution_service import load_constitution
from backend.services.opportunity_service import OpportunityService


def _service(tmp_path: Path) -> tuple[OpportunityService, Database]:
    database = Database(database_path=tmp_path / "opportunity_engine.db")
    database.initialize()
    constitution = load_constitution(Path("config/constitution.json"))
    return OpportunityService(database, constitution), database


def _opportunity_input(**overrides) -> OpportunityInput:
    values = dict(
        title="Cloud Administrator",
        organization_name="Acme Corp",
        description="Manage Azure and AWS environments for our engineering team.",
        source_url="https://example.com/jobs/1",
        location_text="United States",
        remote_status="remote",
        engagement_type="contract",
        tax_type="1099",
        schedule_text="After hours",
        compensation_min=None,
        compensation_max=None,
        compensation_period=None,
        requires_travel=False,
        requires_relocation=False,
        requires_clearance=False,
        replaces_full_time_work=False,
        expires_at=None,
    )
    values.update(overrides)
    return OpportunityInput(**values)


def test_recollecting_a_known_fingerprint_bumps_last_seen_at(tmp_path: Path) -> None:
    service, database = _service(tmp_path)
    opportunity_id, created = service.create_manual(_opportunity_input())
    assert created is True

    with database.session() as session:
        original_last_seen = session.get(Opportunity, opportunity_id).last_seen_at

    _, created_again = service.create_manual(_opportunity_input())
    assert created_again is False

    with database.session() as session:
        updated_last_seen = session.get(Opportunity, opportunity_id).last_seen_at

    assert updated_last_seen >= original_last_seen


def test_expire_stale_opportunities_expires_a_new_opportunity_past_its_expiry(
    tmp_path: Path,
) -> None:
    service, database = _service(tmp_path)
    opportunity_id, _ = service.create_manual(
        _opportunity_input(source_url="https://example.com/jobs/2")
    )
    with database.session() as session:
        session.execute(
            update(Opportunity)
            .where(Opportunity.id == opportunity_id)
            .values(expires_at="2000-01-01T00:00:00.000000Z")
        )
        session.commit()

    expired_ids = service.expire_stale_opportunities()

    assert opportunity_id in expired_ids
    opportunity = service.get_opportunity(opportunity_id)
    assert opportunity["lifecycle_status"] == "expired"

    with database.session() as session:
        events = session.execute(
            select(AuditEventRecord).where(AuditEventRecord.event_type == "opportunity_expired")
        ).scalars().all()
    assert len(events) == 1
    assert events[0].entity_id == opportunity_id


def test_expire_stale_opportunities_leaves_a_future_expiry_alone(tmp_path: Path) -> None:
    service, database = _service(tmp_path)
    opportunity_id, _ = service.create_manual(
        _opportunity_input(source_url="https://example.com/jobs/3")
    )
    with database.session() as session:
        session.execute(
            update(Opportunity)
            .where(Opportunity.id == opportunity_id)
            .values(expires_at="2999-01-01T00:00:00.000000Z")
        )
        session.commit()

    expired_ids = service.expire_stale_opportunities()

    assert opportunity_id not in expired_ids
    opportunity = service.get_opportunity(opportunity_id)
    assert opportunity["lifecycle_status"] != "expired"


def test_expire_stale_opportunities_never_touches_an_already_decided_opportunity(
    tmp_path: Path,
) -> None:
    service, database = _service(tmp_path)
    opportunity_id, _ = service.create_manual(
        _opportunity_input(source_url="https://example.com/jobs/4")
    )
    service.record_review_decision(opportunity_id, "shortlist")
    with database.session() as session:
        session.execute(
            update(Opportunity)
            .where(Opportunity.id == opportunity_id)
            .values(expires_at="2000-01-01T00:00:00.000000Z")
        )
        session.commit()

    expired_ids = service.expire_stale_opportunities()

    assert opportunity_id not in expired_ids
    opportunity = service.get_opportunity(opportunity_id)
    assert opportunity["lifecycle_status"] == "shortlisted"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = Settings(
        database_path=tmp_path / "opportunity_engine.db",
        constitution_path=Path("config/constitution.json"),
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_dashboard_expired_filter_and_age_column(client: TestClient) -> None:
    response = client.post(
        "/opportunities",
        data={
            "title": "Cloud Administrator",
            "organization_name": "Acme Corp",
            "description": "Manage Azure and AWS environments.",
            "source_url": "https://example.com/jobs/5",
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
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    dashboard = client.get("/")
    assert "Age" in dashboard.text
    assert "0 days" in dashboard.text

    expired_filter = client.get("/?status=expired")
    assert expired_filter.status_code == 200
    assert "No opportunities match these filters" in expired_filter.text
