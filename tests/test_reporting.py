"""Tests for pipeline reporting: volume, quality, estimated value (OE-ADR-031)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.adapters.base import RawOpportunityRecord
from backend.app import create_app
from backend.config import Settings
from backend.database import Database
from backend.models import OpportunityInput
from backend.scoring.base import COMPONENT_WEIGHTS, ComponentScore, ScoringResult
from backend.services.collection_service import CollectionService
from backend.services.constitution_service import Constitution, load_constitution
from backend.services.opportunity_service import OpportunityService
from backend.services.reporting_service import ReportingService
from backend.services.scoring_service import ScoringService


class FakeAdapter:
    source_name = "Fake Source"
    source_type = "fake"
    base_url = "https://example.com/fake-feed"

    def __init__(self, records: list[RawOpportunityRecord]) -> None:
        self.records = records

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


class FakeScoringProvider:
    provider_name = "fake"
    model_name = "fake-model"
    scoring_version = "test-v1"
    prompt_version = "test-v1"

    def __init__(self, component_scores: dict[str, float]) -> None:
        self.component_scores = component_scores

    def score(self, opportunity: dict, constitution: Constitution) -> ScoringResult:
        components = [
            ComponentScore(code=code, score=score, explanation=f"Explanation for {code}.")
            for code, score in self.component_scores.items()
        ]
        return ScoringResult(
            components=components,
            confidence=0.9,
            fit_summary="Strong fit for this role.",
            concerns="",
            structured_payload={"components": self.component_scores},
        )


def _setup(tmp_path: Path) -> tuple[OpportunityService, ReportingService, Database, Constitution]:
    database = Database(database_path=tmp_path / "opportunity_engine.db")
    database.initialize()
    constitution = load_constitution(Path("config/constitution.json"))
    return (
        OpportunityService(database, constitution),
        ReportingService(database),
        database,
        constitution,
    )


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


def test_counts_by_status_includes_zero_rows(tmp_path: Path) -> None:
    service, reporting, _, _ = _setup(tmp_path)
    service.create_manual(_opportunity())

    report = reporting.build_report()

    counts = {row["status"]: row["count"] for row in report["by_status"]}
    assert counts["new"] == 1 or counts["eligible"] == 1
    assert counts["rejected"] == 0
    assert set(counts) == {
        "new", "eligible", "ineligible", "shortlisted", "deferred",
        "rejected", "preparing", "expired",
    }


def test_volume_by_source_includes_never_collected_source(tmp_path: Path) -> None:
    _, reporting, database, _ = _setup(tmp_path)
    with database.session() as session:
        OpportunityService.ensure_source(session, "Untouched Source", "fake", None)
        session.commit()

    report = reporting.build_report()

    by_name = {row["name"]: row for row in report["by_source"]}
    assert by_name["Untouched Source"]["run_count"] == 0
    assert by_name["Untouched Source"]["last_run_at"] is None


def test_volume_by_source_aggregates_collection_runs(tmp_path: Path) -> None:
    _, reporting, database, constitution = _setup(tmp_path)
    collection_service = CollectionService(database, constitution)
    adapter = FakeAdapter(
        [
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
    )
    collection_service.run(adapter)

    report = reporting.build_report()

    row = next(r for r in report["by_source"] if r["name"] == "Fake Source")
    assert row["run_count"] == 1
    assert row["records_seen"] == 2
    assert row["records_created"] == 2
    assert row["last_run_at"] is not None


def test_quality_summary_uses_only_the_latest_scoring_run(tmp_path: Path) -> None:
    service, reporting, database, constitution = _setup(tmp_path)
    opportunity_id, _ = service.create_manual(_opportunity())

    low_scores = {code: 20.0 for code in COMPONENT_WEIGHTS}
    high_scores = {code: 90.0 for code in COMPONENT_WEIGHTS}
    ScoringService(database, constitution, FakeScoringProvider(low_scores)).score_opportunity(
        opportunity_id
    )
    ScoringService(database, constitution, FakeScoringProvider(high_scores)).score_opportunity(
        opportunity_id
    )

    quality = reporting.build_report()["quality"]

    assert quality["scored_count"] == 1
    assert quality["avg_score"] > 80.0


def test_quality_summary_breaks_down_by_status(tmp_path: Path) -> None:
    service, reporting, database, constitution = _setup(tmp_path)
    opportunity_id, _ = service.create_manual(_opportunity())
    ScoringService(
        database, constitution, FakeScoringProvider({code: 75.0 for code in COMPONENT_WEIGHTS})
    ).score_opportunity(opportunity_id)
    service.record_review_decision(opportunity_id, "shortlist")

    quality = reporting.build_report()["quality"]

    by_status = {row["status"]: row for row in quality["by_status"]}
    assert by_status["shortlisted"]["count"] == 1
    assert by_status["shortlisted"]["avg_score"] == pytest.approx(75.0)


def test_value_by_period_excludes_terminal_statuses_and_merges_unspecified(
    tmp_path: Path,
) -> None:
    service, reporting, _, _ = _setup(tmp_path)
    active_id, _ = service.create_manual(
        _opportunity(
            title="Hourly Contract Role",
            source_url="https://example.com/jobs/hourly",
            compensation_min=50.0,
            compensation_max=90.0,
            compensation_period="hour",
        )
    )
    service.create_manual(
        _opportunity(
            title="Unspecified Comp Role",
            source_url="https://example.com/jobs/unspecified",
            requires_clearance=None,
        )
    )
    rejected_id, _ = service.create_manual(
        _opportunity(
            title="Rejected Hourly Role",
            source_url="https://example.com/jobs/rejected-hourly",
            compensation_min=200.0,
            compensation_max=300.0,
            compensation_period="hour",
        )
    )
    service.record_review_decision(rejected_id, "reject")

    report = reporting.build_report()

    by_period = {row["period"]: row for row in report["value_by_period"]}
    assert by_period["hour"]["count"] == 1
    assert by_period["hour"]["min"] == 50.0
    assert by_period["hour"]["max"] == 90.0
    assert "unspecified" in by_period
    assert by_period["unspecified"]["count"] >= 1
    assert sum(row["count"] for row in report["value_by_period"]) == 2


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


def test_reports_route_renders(client: TestClient) -> None:
    client.post("/opportunities", data=_form(), follow_redirects=False)

    response = client.get("/reports")

    assert response.status_code == 200
    assert "Pipeline report" in response.text
    assert "Volume by status" in response.text
    assert "Estimated value by pay type" in response.text
