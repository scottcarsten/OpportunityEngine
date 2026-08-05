"""Likely-duplicate detection tests (similarity review, ARCHITECTURE.md §5.3)."""

from pathlib import Path

from sqlalchemy import select

from backend.database import Database
from backend.db.models import DeduplicationDecision
from backend.models import OpportunityInput
from backend.services.constitution_service import load_constitution
from backend.services.opportunity_service import OpportunityService


def _service(tmp_path: Path) -> OpportunityService:
    database = Database(database_path=tmp_path / "opportunity_engine.db")
    database.initialize()
    constitution = load_constitution(Path("config/constitution.json"))
    return OpportunityService(database, constitution)


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


def test_near_identical_listing_creates_likely_duplicate(tmp_path: Path) -> None:
    service = _service(tmp_path)

    first_id, _ = service.create_manual(_opportunity())
    second_id, _ = service.create_manual(
        _opportunity(
            source_url="https://example.com/jobs/2",
            description="Manage Azure and AWS environments for our engineering teams.",
        )
    )

    assert first_id != second_id

    with service.database.session() as session:
        decisions = session.execute(select(DeduplicationDecision)).scalars().all()

    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.retained_opportunity_id == first_id
    assert decision.duplicate_opportunity_id == second_id
    assert decision.method == "similarity"
    assert decision.decided_by == "system"
    assert 0.85 <= decision.confidence <= 1.0


def test_unrelated_organization_creates_no_duplicate_decision(tmp_path: Path) -> None:
    service = _service(tmp_path)

    service.create_manual(_opportunity())
    service.create_manual(
        _opportunity(
            organization_name="Totally Different Inc",
            title="Network Engineer",
            description="Design and operate our WAN and datacenter fabric.",
            source_url="https://example.com/jobs/3",
        )
    )

    with service.database.session() as session:
        decisions = session.execute(select(DeduplicationDecision)).scalars().all()

    assert decisions == []


def test_exact_duplicate_still_short_circuits_before_similarity_check(tmp_path: Path) -> None:
    service = _service(tmp_path)

    first_id, first_created = service.create_manual(_opportunity())
    second_id, second_created = service.create_manual(_opportunity())

    assert first_created is True
    assert second_created is False
    assert first_id == second_id

    with service.database.session() as session:
        decisions = session.execute(select(DeduplicationDecision)).scalars().all()

    assert decisions == []
