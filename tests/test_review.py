"""Review-decision and internal-notification tests (Milestone 5)."""

from pathlib import Path
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app import create_app
from backend.config import Settings
from backend.database import Database
from backend.db.models import AuditEventRecord, Notification, ReviewDecision
from backend.models import OpportunityInput
from backend.services.constitution_service import Constitution, load_constitution
from backend.services.opportunity_service import OpportunityService


def _opportunity_service(tmp_path: Path) -> tuple[OpportunityService, Database, Constitution]:
    database = Database(database_path=tmp_path / "opportunity_engine.db")
    database.initialize()
    constitution = load_constitution(Path("config/constitution.json"))
    return OpportunityService(database, constitution), database, constitution


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


def test_shortlist_decision_updates_status_and_is_audited(tmp_path: Path) -> None:
    service, database, _ = _opportunity_service(tmp_path)
    opportunity_id, _ = service.create_manual(_opportunity())

    service.record_review_decision(opportunity_id, "shortlist", "Strong fit.")

    opportunity = service.get_opportunity(opportunity_id)
    assert opportunity["lifecycle_status"] == "shortlisted"
    assert len(opportunity["review_decisions"]) == 1
    assert opportunity["review_decisions"][0]["decision"] == "shortlist"
    assert opportunity["review_decisions"][0]["rationale"] == "Strong fit."

    with database.session() as session:
        audit_events = session.execute(
            select(AuditEventRecord).where(AuditEventRecord.event_type == "review_decision")
        ).scalars().all()
    assert len(audit_events) == 1
    assert audit_events[0].entity_id == opportunity_id


@pytest.mark.parametrize(
    "decision,expected_status",
    [
        ("shortlist", "shortlisted"),
        ("reject", "rejected"),
        ("defer", "deferred"),
        ("request_preparation", "preparing"),
        ("reopen", "eligible"),
    ],
)
def test_each_decision_maps_to_its_lifecycle_status(
    tmp_path: Path, decision: str, expected_status: str
) -> None:
    service, _, _ = _opportunity_service(tmp_path)
    opportunity_id, _ = service.create_manual(_opportunity())

    service.record_review_decision(opportunity_id, decision)

    opportunity = service.get_opportunity(opportunity_id)
    assert opportunity["lifecycle_status"] == expected_status


def test_invalid_decision_raises(tmp_path: Path) -> None:
    service, _, _ = _opportunity_service(tmp_path)
    opportunity_id, _ = service.create_manual(_opportunity())

    with pytest.raises(ValueError, match="unsupported review decision"):
        service.record_review_decision(opportunity_id, "bogus")


def test_redeciding_records_a_second_row_not_an_update(tmp_path: Path) -> None:
    service, database, _ = _opportunity_service(tmp_path)
    opportunity_id, _ = service.create_manual(_opportunity())

    service.record_review_decision(opportunity_id, "shortlist")
    service.record_review_decision(opportunity_id, "reject", "Changed my mind.")

    with database.session() as session:
        decisions = session.execute(
            select(ReviewDecision).where(ReviewDecision.opportunity_id == opportunity_id)
        ).scalars().all()
    assert len(decisions) == 2

    opportunity = service.get_opportunity(opportunity_id)
    assert opportunity["lifecycle_status"] == "rejected"


def test_notification_created_for_eligible_and_new_not_ineligible(tmp_path: Path) -> None:
    service, database, _ = _opportunity_service(tmp_path)

    eligible_id, _ = service.create_manual(_opportunity(source_url="https://example.com/jobs/1"))
    new_id, _ = service.create_manual(
        _opportunity(
            title="Unclear Administrator",
            source_url="https://example.com/jobs/2",
            requires_clearance=None,
        )
    )
    ineligible_id, _ = service.create_manual(
        _opportunity(
            title="Traveling Administrator",
            source_url="https://example.com/jobs/3",
            requires_travel=True,
        )
    )

    with database.session() as session:
        notified_opportunity_ids = {
            row[0]
            for row in session.execute(
                select(Notification.opportunity_id).where(Notification.status == "queued")
            ).all()
        }

    assert eligible_id in notified_opportunity_ids
    assert new_id in notified_opportunity_ids
    assert ineligible_id not in notified_opportunity_ids
    assert service.count_pending_review() == 2


def test_mark_notifications_sent_flips_status_and_count(tmp_path: Path) -> None:
    service, database, _ = _opportunity_service(tmp_path)
    opportunity_id, _ = service.create_manual(_opportunity())
    assert service.count_pending_review() == 1

    service.mark_notifications_sent(opportunity_id)

    assert service.count_pending_review() == 0
    with database.session() as session:
        notification = session.execute(
            select(Notification).where(Notification.opportunity_id == opportunity_id)
        ).scalar_one()
    assert notification.status == "sent"
    assert notification.sent_at is not None


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


def test_review_route_updates_badge_and_history(client: TestClient) -> None:
    created = client.post("/opportunities", data=_form(), follow_redirects=False)
    detail_path = urlparse(created.headers["location"]).path

    response = client.post(
        f"{detail_path}/review",
        data={"decision": "shortlist", "rationale": "Great fit."},
        follow_redirects=False,
    )
    assert response.status_code == 303

    detail = client.get(detail_path)
    assert "Shortlisted" in detail.text
    assert "Great fit." in detail.text


def test_review_route_rejects_invalid_decision(client: TestClient) -> None:
    created = client.post("/opportunities", data=_form(), follow_redirects=False)
    detail_path = urlparse(created.headers["location"]).path

    response = client.post(
        f"{detail_path}/review", data={"decision": "bogus"}, follow_redirects=False
    )
    assert response.status_code == 422


def test_dashboard_banner_reflects_pending_review_and_clears_on_view(
    client: TestClient,
) -> None:
    created = client.post("/opportunities", data=_form(), follow_redirects=False)
    detail_path = urlparse(created.headers["location"]).path

    dashboard_before = client.get("/")
    assert "need" in dashboard_before.text and "your review" in dashboard_before.text

    client.get(detail_path)  # viewing marks its notification sent

    dashboard_after = client.get("/")
    assert "your review" not in dashboard_after.text
