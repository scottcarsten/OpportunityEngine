"""Explainable-scoring tests: service logic and route, no live Opus 5 calls."""

from pathlib import Path
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app import create_app
from backend.config import Settings
from backend.database import Database
from backend.db.models import ScoreComponent, ScoringRun
from backend.models import OpportunityInput
from backend.scoring.base import COMPONENT_WEIGHTS, ComponentScore, ScoringResult
from backend.services.constitution_service import Constitution, load_constitution
from backend.services.opportunity_service import OpportunityService
from backend.services.scoring_service import ScoringService


class FakeScoringProvider:
    provider_name = "fake"
    model_name = "fake-model"
    scoring_version = "test-v1"
    prompt_version = "test-v1"

    def __init__(
        self,
        component_scores: dict[str, float] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.component_scores = component_scores or {code: 80.0 for code in COMPONENT_WEIGHTS}
        self.error = error
        self.calls = 0

    def score(self, opportunity: dict, constitution: Constitution) -> ScoringResult:
        self.calls += 1
        if self.error is not None:
            raise self.error
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


def _opportunity_service(tmp_path: Path) -> tuple[OpportunityService, Database, Constitution]:
    database = Database(database_path=tmp_path / "opportunity_engine.db")
    database.initialize()
    constitution = load_constitution(Path("config/constitution.json"))
    return OpportunityService(database, constitution), database, constitution


def _eligible_opportunity(service: OpportunityService) -> int:
    opportunity_id, _ = service.create_manual(
        OpportunityInput(
            title="Cloud Administrator",
            organization_name="Acme Corp",
            description="Manage Azure and AWS environments for our engineering team.",
            source_url="https://example.com/jobs/1",
            location_text="United States",
            remote_status="remote",
            engagement_type="contract",
            tax_type="1099",
            schedule_text="After hours",
            compensation_min=85,
            compensation_max=125,
            compensation_period="hour",
            requires_travel=False,
            requires_relocation=False,
            requires_clearance=False,
            replaces_full_time_work=False,
        )
    )
    return opportunity_id


def _ineligible_opportunity(service: OpportunityService) -> int:
    opportunity_id, _ = service.create_manual(
        OpportunityInput(
            title="Traveling Administrator",
            organization_name="Acme Corp",
            description="On-site travel required across client sites.",
            source_url="https://example.com/jobs/2",
            location_text="United States",
            remote_status="remote",
            engagement_type="contract",
            tax_type="1099",
            schedule_text="After hours",
            compensation_min=None,
            compensation_max=None,
            compensation_period=None,
            requires_travel=True,
            requires_relocation=False,
            requires_clearance=False,
            replaces_full_time_work=False,
        )
    )
    return opportunity_id


def test_scoring_ineligible_opportunity_raises(tmp_path: Path) -> None:
    opp_service, database, constitution = _opportunity_service(tmp_path)
    opportunity_id = _ineligible_opportunity(opp_service)

    scoring_service = ScoringService(database, constitution, FakeScoringProvider())
    with pytest.raises(ValueError, match="hard filters"):
        scoring_service.score_opportunity(opportunity_id)


def test_scoring_eligible_opportunity_creates_run_and_components(tmp_path: Path) -> None:
    opp_service, database, constitution = _opportunity_service(tmp_path)
    opportunity_id = _eligible_opportunity(opp_service)

    scoring_service = ScoringService(database, constitution, FakeScoringProvider())
    result = scoring_service.score_opportunity(opportunity_id)

    assert result["status"] == "succeeded"
    assert result["overall_score"] == pytest.approx(80.0)

    with database.session() as session:
        runs = session.execute(select(ScoringRun)).scalars().all()
        components = session.execute(select(ScoreComponent)).scalars().all()

    assert len(runs) == 1
    assert runs[0].status == "succeeded"
    assert runs[0].provider == "fake"
    assert len(components) == len(COMPONENT_WEIGHTS)
    assert sum(c.weight for c in components) == pytest.approx(1.0)


def test_scoring_a_preparing_opportunity_still_works(tmp_path: Path) -> None:
    opp_service, database, constitution = _opportunity_service(tmp_path)
    opportunity_id = _eligible_opportunity(opp_service)
    opp_service.record_review_decision(opportunity_id, "request_preparation")

    scoring_service = ScoringService(database, constitution, FakeScoringProvider())
    result = scoring_service.score_opportunity(opportunity_id)

    assert result["status"] == "succeeded"
    opportunity = opp_service.get_opportunity(opportunity_id)
    assert opportunity["lifecycle_status"] == "preparing"


def test_rescoring_creates_a_second_run_not_an_update(tmp_path: Path) -> None:
    opp_service, database, constitution = _opportunity_service(tmp_path)
    opportunity_id = _eligible_opportunity(opp_service)
    scoring_service = ScoringService(database, constitution, FakeScoringProvider())

    scoring_service.score_opportunity(opportunity_id)
    scoring_service.score_opportunity(opportunity_id)

    with database.session() as session:
        runs = session.execute(select(ScoringRun)).scalars().all()
        opportunity = opp_service.get_opportunity(opportunity_id)

    assert len(runs) == 2
    assert opportunity["lifecycle_status"] == "eligible"


def test_provider_failure_records_a_failed_run(tmp_path: Path) -> None:
    opp_service, database, constitution = _opportunity_service(tmp_path)
    opportunity_id = _eligible_opportunity(opp_service)
    scoring_service = ScoringService(
        database, constitution, FakeScoringProvider(error=RuntimeError("boom"))
    )

    result = scoring_service.score_opportunity(opportunity_id)

    assert result["status"] == "failed"
    assert "boom" in result["error_summary"]

    with database.session() as session:
        runs = session.execute(select(ScoringRun)).scalars().all()
        components = session.execute(select(ScoreComponent)).scalars().all()

    assert len(runs) == 1
    assert runs[0].status == "failed"
    assert "boom" in runs[0].error_summary
    assert components == []


@pytest.fixture
def client_and_app(tmp_path: Path):
    settings = Settings(
        database_path=tmp_path / "opportunity_engine.db",
        constitution_path=Path("config/constitution.json"),
    )
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client, app


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
        "compensation_min": "85",
        "compensation_max": "125",
        "compensation_period": "hour",
        "requires_travel": "no",
        "requires_relocation": "no",
        "requires_clearance": "no",
        "replaces_full_time_work": "no",
    }
    values.update(overrides)
    return values


def test_score_route_renders_fit_score_section(client_and_app) -> None:
    client, app = client_and_app
    app.state.scoring_provider = FakeScoringProvider()

    created = client.post("/opportunities", data=_form(), follow_redirects=False)
    detail_path = urlparse(created.headers["location"]).path

    response = client.post(f"{detail_path}/score", follow_redirects=False)
    assert response.status_code == 303

    detail = client.get(detail_path)
    assert "Fit score" in detail.text
    assert "80/100" in detail.text
    assert "Advisory only" in detail.text


def test_score_route_rejects_non_eligible_opportunity(client_and_app) -> None:
    client, app = client_and_app
    app.state.scoring_provider = FakeScoringProvider()

    created = client.post(
        "/opportunities",
        data=_form(title="Traveling Administrator", requires_travel="yes"),
        follow_redirects=False,
    )
    detail_path = urlparse(created.headers["location"]).path

    response = client.post(f"{detail_path}/score", follow_redirects=False)
    assert response.status_code == 422
