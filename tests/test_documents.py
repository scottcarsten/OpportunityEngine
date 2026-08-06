"""Application-document generation tests: service logic and route, no live Opus 5 calls."""

import json
from pathlib import Path
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app import create_app
from backend.config import Settings
from backend.database import Database
from backend.db.models import AuditEventRecord, GeneratedDocument, ScoreComponent, ScoringRun
from backend.documents.base import DocumentGenerationResult
from backend.models import OpportunityInput
from backend.services.constitution_service import Constitution, load_constitution
from backend.services.document_service import DocumentService
from backend.services.opportunity_service import OpportunityService
from backend.services.resume_service import ResumeService
from backend.timeutil import now_iso


class FakeDocumentProvider:
    provider_name = "fake"
    model_name = "fake-model"
    prompt_version = "test-v1"

    def __init__(
        self,
        unsupported_claims: list[str] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.unsupported_claims = unsupported_claims or []
        self.error = error
        self.calls = 0
        self.last_scoring: dict | None = None

    def generate_tailored_resume(self, opportunity, master_resume, resume_bytes, constitution):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return DocumentGenerationResult(
            content=f"Tailored résumé for {opportunity['title']}, grounded in "
            f"{resume_bytes.decode('utf-8')}.",
            unsupported_claims=self.unsupported_claims,
            structured_payload={"unsupported_claims": self.unsupported_claims},
        )

    def generate_cover_letter(self, opportunity, master_resume, resume_bytes, constitution):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return DocumentGenerationResult(
            content=f"Cover letter for {opportunity['title']}, grounded in "
            f"{resume_bytes.decode('utf-8')}.",
            unsupported_claims=self.unsupported_claims,
            structured_payload={"unsupported_claims": self.unsupported_claims},
        )

    def generate_fit_report(self, opportunity, master_resume, resume_bytes, scoring, constitution):
        self.calls += 1
        self.last_scoring = scoring
        if self.error is not None:
            raise self.error
        return DocumentGenerationResult(
            content=f"Fit report for {opportunity['title']}: {scoring['fit_summary']}.",
            unsupported_claims=self.unsupported_claims,
            structured_payload={"unsupported_claims": self.unsupported_claims},
        )


def _services(tmp_path: Path) -> tuple[OpportunityService, ResumeService, Database, Constitution]:
    database = Database(database_path=tmp_path / "opportunity_engine.db")
    database.initialize()
    constitution = load_constitution(Path("config/constitution.json"))
    opportunity_service = OpportunityService(database, constitution)
    resume_service = ResumeService(database, constitution, storage_path=tmp_path / "resumes")
    return opportunity_service, resume_service, database, constitution


def _preparing_opportunity(service: OpportunityService) -> int:
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
    service.record_review_decision(opportunity_id, "request_preparation")
    return opportunity_id


def test_generation_requires_preparing_status(tmp_path: Path) -> None:
    opp_service, resume_service, database, constitution = _services(tmp_path)
    opportunity_id, _ = opp_service.create_manual(
        OpportunityInput(
            title="Cloud Administrator",
            organization_name="Acme Corp",
            description="Manage Azure and AWS environments.",
            source_url="https://example.com/jobs/2",
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
        )
    )
    document_service = DocumentService(
        database, constitution, FakeDocumentProvider(), resume_service, tmp_path / "documents"
    )

    with pytest.raises(ValueError, match="preparing"):
        document_service.generate_tailored_resume(opportunity_id)


def test_generation_requires_a_master_resume(tmp_path: Path) -> None:
    opp_service, resume_service, database, constitution = _services(tmp_path)
    opportunity_id = _preparing_opportunity(opp_service)
    document_service = DocumentService(
        database, constitution, FakeDocumentProvider(), resume_service, tmp_path / "documents"
    )

    with pytest.raises(ValueError, match="master résumé"):
        document_service.generate_tailored_resume(opportunity_id)


def test_clean_generation_creates_ready_for_review_document(tmp_path: Path) -> None:
    opp_service, resume_service, database, constitution = _services(tmp_path)
    opportunity_id = _preparing_opportunity(opp_service)
    resume_service.import_master_resume("resume.txt", b"Master resume content.", "text/plain")
    document_service = DocumentService(
        database, constitution, FakeDocumentProvider(), resume_service, tmp_path / "documents"
    )

    result = document_service.generate_tailored_resume(opportunity_id)

    assert result["status"] == "ready_for_review"
    assert result["version"] == 1
    assert result["unsupported_claims"] == []

    with database.session() as session:
        docs = session.execute(select(GeneratedDocument)).scalars().all()
    assert len(docs) == 1
    assert docs[0].document_type == "tailored_resume"
    assert docs[0].status == "ready_for_review"
    assert Path(docs[0].storage_path).is_file()


def test_generation_with_unsupported_claims_is_flagged(tmp_path: Path) -> None:
    opp_service, resume_service, database, constitution = _services(tmp_path)
    opportunity_id = _preparing_opportunity(opp_service)
    resume_service.import_master_resume("resume.txt", b"Master resume content.", "text/plain")
    provider = FakeDocumentProvider(unsupported_claims=["Invented a AWS certification."])
    document_service = DocumentService(
        database, constitution, provider, resume_service, tmp_path / "documents"
    )

    result = document_service.generate_tailored_resume(opportunity_id)

    assert result["status"] == "validation_failed"
    assert result["unsupported_claims"] == ["Invented a AWS certification."]

    with database.session() as session:
        doc = session.execute(select(GeneratedDocument)).scalars().one()
    assert doc.status == "validation_failed"
    assert json.loads(doc.unsupported_claims_json) == ["Invented a AWS certification."]


def test_regenerating_creates_a_second_version_not_an_update(tmp_path: Path) -> None:
    opp_service, resume_service, database, constitution = _services(tmp_path)
    opportunity_id = _preparing_opportunity(opp_service)
    resume_service.import_master_resume("resume.txt", b"Master resume content.", "text/plain")
    document_service = DocumentService(
        database, constitution, FakeDocumentProvider(), resume_service, tmp_path / "documents"
    )

    document_service.generate_tailored_resume(opportunity_id)
    second = document_service.generate_tailored_resume(opportunity_id)

    assert second["version"] == 2
    with database.session() as session:
        docs = session.execute(select(GeneratedDocument)).scalars().all()
    assert len(docs) == 2
    assert sorted(doc.version for doc in docs) == [1, 2]


def _seed_successful_scoring(database: Database, opportunity_id: int) -> None:
    with database.session() as session:
        run = ScoringRun(
            opportunity_id=opportunity_id,
            status="succeeded",
            scoring_version="test-v1",
            provider="fake",
            model="fake-model",
            prompt_version="test-v1",
            input_hash="deadbeef",
            overall_score=82.5,
            confidence=0.9,
            fit_summary="Strong fit for this role.",
            concerns="Compensation not specified.",
            correlation_id="test-correlation",
            started_at=now_iso(),
            completed_at=now_iso(),
        )
        session.add(run)
        session.flush()
        session.add(
            ScoreComponent(
                scoring_run_id=run.id,
                component_code="skills_alignment",
                score=90.0,
                weight=0.35,
                explanation="Strong Azure/AWS overlap.",
            )
        )
        session.commit()


def test_cover_letter_generation_creates_ready_for_review_document(tmp_path: Path) -> None:
    opp_service, resume_service, database, constitution = _services(tmp_path)
    opportunity_id = _preparing_opportunity(opp_service)
    resume_service.import_master_resume("resume.txt", b"Master resume content.", "text/plain")
    document_service = DocumentService(
        database, constitution, FakeDocumentProvider(), resume_service, tmp_path / "documents"
    )

    result = document_service.generate_cover_letter(opportunity_id)

    assert result["status"] == "ready_for_review"
    with database.session() as session:
        doc = session.execute(select(GeneratedDocument)).scalars().one()
    assert doc.document_type == "cover_letter"


def test_fit_report_requires_successful_scoring(tmp_path: Path) -> None:
    opp_service, resume_service, database, constitution = _services(tmp_path)
    opportunity_id = _preparing_opportunity(opp_service)
    resume_service.import_master_resume("resume.txt", b"Master resume content.", "text/plain")
    document_service = DocumentService(
        database, constitution, FakeDocumentProvider(), resume_service, tmp_path / "documents"
    )

    with pytest.raises(ValueError, match="score this opportunity"):
        document_service.generate_fit_report(opportunity_id)


def test_fit_report_synthesizes_the_latest_successful_scoring_run(tmp_path: Path) -> None:
    opp_service, resume_service, database, constitution = _services(tmp_path)
    opportunity_id = _preparing_opportunity(opp_service)
    resume_service.import_master_resume("resume.txt", b"Master resume content.", "text/plain")
    _seed_successful_scoring(database, opportunity_id)
    provider = FakeDocumentProvider()
    document_service = DocumentService(
        database, constitution, provider, resume_service, tmp_path / "documents"
    )

    result = document_service.generate_fit_report(opportunity_id)

    assert result["status"] == "ready_for_review"
    with database.session() as session:
        doc = session.execute(select(GeneratedDocument)).scalars().one()
    assert doc.document_type == "fit_report"
    assert provider.last_scoring["overall_score"] == 82.5
    assert provider.last_scoring["fit_summary"] == "Strong fit for this role."
    assert provider.last_scoring["components"][0]["code"] == "skills_alignment"


def test_provider_failure_records_audit_event_and_no_document(tmp_path: Path) -> None:
    opp_service, resume_service, database, constitution = _services(tmp_path)
    opportunity_id = _preparing_opportunity(opp_service)
    resume_service.import_master_resume("resume.txt", b"Master resume content.", "text/plain")
    document_service = DocumentService(
        database,
        constitution,
        FakeDocumentProvider(error=RuntimeError("boom")),
        resume_service,
        tmp_path / "documents",
    )

    with pytest.raises(RuntimeError, match="boom"):
        document_service.generate_tailored_resume(opportunity_id)

    with database.session() as session:
        docs = session.execute(select(GeneratedDocument)).scalars().all()
        events = session.execute(
            select(AuditEventRecord).where(
                AuditEventRecord.event_type == "document_generation_failed"
            )
        ).scalars().all()
    assert docs == []
    assert len(events) == 1
    assert "boom" in events[0].summary


@pytest.fixture
def client_and_app(tmp_path: Path):
    settings = Settings(
        database_path=tmp_path / "opportunity_engine.db",
        constitution_path=Path("config/constitution.json"),
        resume_storage_path=tmp_path / "resumes",
        document_storage_path=tmp_path / "documents",
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


def test_generation_route_renders_draft_and_flags_claims(client_and_app) -> None:
    client, app = client_and_app
    app.state.document_provider = FakeDocumentProvider(
        unsupported_claims=["Invented a AWS certification."]
    )

    client.post(
        "/resume",
        files={"file": ("resume.txt", b"Master resume content.", "text/plain")},
        follow_redirects=False,
    )
    created = client.post("/opportunities", data=_form(), follow_redirects=False)
    detail_path = urlparse(created.headers["location"]).path

    client.post(f"{detail_path}/review", data={"decision": "request_preparation"})

    response = client.post(
        f"{detail_path}/documents/tailored-resume", follow_redirects=False
    )
    assert response.status_code == 303

    detail = client.get(detail_path)
    assert "Tailored r" in detail.text
    assert "Validation failed" in detail.text
    assert "Invented a AWS certification." in detail.text


def test_generation_route_rejects_non_preparing_opportunity(client_and_app) -> None:
    client, app = client_and_app
    app.state.document_provider = FakeDocumentProvider()

    created = client.post("/opportunities", data=_form(), follow_redirects=False)
    detail_path = urlparse(created.headers["location"]).path

    response = client.post(
        f"{detail_path}/documents/tailored-resume", follow_redirects=False
    )
    assert response.status_code == 422


def test_cover_letter_route_renders_draft(client_and_app) -> None:
    client, app = client_and_app
    app.state.document_provider = FakeDocumentProvider()

    client.post(
        "/resume",
        files={"file": ("resume.txt", b"Master resume content.", "text/plain")},
        follow_redirects=False,
    )
    created = client.post("/opportunities", data=_form(), follow_redirects=False)
    detail_path = urlparse(created.headers["location"]).path
    client.post(f"{detail_path}/review", data={"decision": "request_preparation"})

    response = client.post(f"{detail_path}/documents/cover-letter", follow_redirects=False)
    assert response.status_code == 303

    detail = client.get(detail_path)
    assert "Cover letter" in detail.text
    assert "Ready for review" in detail.text


def test_fit_report_route_requires_scoring_first(client_and_app) -> None:
    client, app = client_and_app
    app.state.document_provider = FakeDocumentProvider()

    client.post(
        "/resume",
        files={"file": ("resume.txt", b"Master resume content.", "text/plain")},
        follow_redirects=False,
    )
    created = client.post("/opportunities", data=_form(), follow_redirects=False)
    detail_path = urlparse(created.headers["location"]).path
    client.post(f"{detail_path}/review", data={"decision": "request_preparation"})

    response = client.post(f"{detail_path}/documents/fit-report", follow_redirects=False)
    assert response.status_code == 422
