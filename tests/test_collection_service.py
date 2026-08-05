"""CollectionService tests: idempotent collection with a fake adapter."""

from pathlib import Path

from sqlalchemy import select

from backend.adapters.base import RawOpportunityRecord
from backend.database import Database
from backend.db.models import CollectionRun, Opportunity, SourceRecord
from backend.models import OpportunityInput
from backend.services.collection_service import CollectionService
from backend.services.constitution_service import load_constitution


class FakeAdapter:
    source_name = "Fake Source"
    source_type = "fake"
    base_url = "https://example.com/fake-feed"

    def __init__(self) -> None:
        self.records = [
            RawOpportunityRecord(
                external_id="job-1",
                canonical_url="https://example.com/jobs/1",
                retrieved_at="2026-08-05T00:00:00.000000Z",
                raw_payload={"title": "Fake Co: Systems Administrator"},
            ),
            RawOpportunityRecord(
                external_id="job-2",
                canonical_url="https://example.com/jobs/2",
                retrieved_at="2026-08-05T00:00:00.000000Z",
                raw_payload={"title": "Fake Co: Cloud Engineer"},
            ),
        ]

    def fetch(self) -> list[RawOpportunityRecord]:
        return self.records

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


def _service(tmp_path: Path) -> CollectionService:
    database = Database(database_path=tmp_path / "opportunity_engine.db")
    database.initialize()
    constitution = load_constitution(Path("config/constitution.json"))
    return CollectionService(database, constitution)


def test_first_run_creates_opportunities_and_source_records(tmp_path: Path) -> None:
    service = _service(tmp_path)
    adapter = FakeAdapter()

    result = service.run(adapter)

    assert result["status"] == "succeeded"
    assert result["records_seen"] == 2
    assert result["records_created"] == 2
    assert result["records_updated"] == 0

    with service.database.session() as session:
        opportunity_count = len(session.execute(select(Opportunity.id)).all())
        source_record_count = len(session.execute(select(SourceRecord.id)).all())
        run_count = len(session.execute(select(CollectionRun.id)).all())
    assert opportunity_count == 2
    assert source_record_count == 2
    assert run_count == 1


def test_second_run_is_idempotent(tmp_path: Path) -> None:
    service = _service(tmp_path)
    adapter = FakeAdapter()

    service.run(adapter)
    second_result = service.run(adapter)

    assert second_result["status"] == "succeeded"
    assert second_result["records_seen"] == 2
    assert second_result["records_created"] == 0
    assert second_result["records_updated"] == 2

    with service.database.session() as session:
        opportunity_count = len(session.execute(select(Opportunity.id)).all())
        source_record_count = len(session.execute(select(SourceRecord.id)).all())
        run_count = len(session.execute(select(CollectionRun.id)).all())
    assert opportunity_count == 2
    assert source_record_count == 2
    assert run_count == 2
