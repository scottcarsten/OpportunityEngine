"""Application-document generation: résumé, cover letter, fit report."""

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Literal

from sqlalchemy import select, update

from backend.database import Database
from backend.db.models import GeneratedDocument, Opportunity, ScoreComponent, ScoringRun
from backend.documents.base import DocumentGenerationProvider, DocumentGenerationResult
from backend.services.audit_service import AuditEvent, AuditService
from backend.services.constitution_service import Constitution
from backend.services.resume_service import ResumeService
from backend.timeutil import now_iso

_DECIDABLE_STATUSES = ("ready_for_review", "validation_failed")
_DECISION_STATUS: dict[str, str] = {"approve": "approved", "reject": "rejected"}


class DocumentService:
    """Generate tailored-résumé, cover-letter, and fit-report drafts.

    Generation requires `lifecycle_status == "preparing"` — Scott's own
    `request_preparation` review decision — not just "eligible" or
    "scored", matching the constitution's "notify, then wait for explicit
    approval" pipeline. A provider failure records an audit event but
    writes no `generated_documents` row, since the schema's `status`
    check constraint has no failure state (`OE-ADR-020`). A fit report
    additionally requires a successful scoring run to synthesize
    (`OE-ADR-023`).
    """

    def __init__(
        self,
        database: Database,
        constitution: Constitution,
        provider: DocumentGenerationProvider,
        resume_service: ResumeService,
        storage_path: Path,
    ) -> None:
        self.database = database
        self.constitution = constitution
        self.provider = provider
        self.resume_service = resume_service
        self.storage_path = storage_path

    def generate_tailored_resume(self, opportunity_id: int) -> dict:
        opportunity_dict, master, resume_bytes = self._prepare(opportunity_id)
        result = self._run_provider(
            "tailored_resume",
            opportunity_id,
            lambda: self.provider.generate_tailored_resume(
                opportunity_dict, master, resume_bytes, self.constitution
            ),
        )
        return self._persist("tailored_resume", opportunity_id, master, result)

    def generate_cover_letter(self, opportunity_id: int) -> dict:
        opportunity_dict, master, resume_bytes = self._prepare(opportunity_id)
        result = self._run_provider(
            "cover_letter",
            opportunity_id,
            lambda: self.provider.generate_cover_letter(
                opportunity_dict, master, resume_bytes, self.constitution
            ),
        )
        return self._persist("cover_letter", opportunity_id, master, result)

    def generate_fit_report(self, opportunity_id: int) -> dict:
        opportunity_dict, master, resume_bytes = self._prepare(opportunity_id)
        scoring = self._latest_successful_scoring(opportunity_id)
        if scoring is None:
            raise ValueError(
                "score this opportunity before generating a fit report"
            )
        result = self._run_provider(
            "fit_report",
            opportunity_id,
            lambda: self.provider.generate_fit_report(
                opportunity_dict, master, resume_bytes, scoring, self.constitution
            ),
        )
        return self._persist("fit_report", opportunity_id, master, result)

    def record_approval_decision(
        self,
        document_id: int,
        decision: Literal["approve", "reject"],
        rationale: str | None = None,
    ) -> None:
        """Approve or reject a draft. Permanent — see `OE-ADR-024`.

        `validation_failed` documents remain approvable: flagged claims
        are Scott's judgment call, not an automatic block. Once decided,
        the DB trigger (`protect_generated_document_update`) makes the
        row immutable; this pre-check exists only for a friendlier error
        than the raw `IntegrityError` that trigger would raise.
        """
        new_status = _DECISION_STATUS[decision]
        with self.database.session() as session:
            document = session.execute(
                select(GeneratedDocument).where(GeneratedDocument.id == document_id)
            ).scalar_one_or_none()
            if document is None:
                raise ValueError(f"document not found: {document_id}")
            if document.status not in _DECIDABLE_STATUSES:
                raise ValueError(
                    f"document {document_id} has already been decided "
                    f"(status={document.status})"
                )

            reviewed_at = now_iso()
            session.execute(
                update(GeneratedDocument)
                .where(GeneratedDocument.id == document_id)
                .values(status=new_status, reviewed_at=reviewed_at)
            )
            AuditService(session).record(
                AuditEvent(
                    event_type=f"document_{new_status}",
                    actor_type="scott",
                    entity_type="generated_document",
                    entity_id=document_id,
                    constitution_version=self.constitution.version,
                    summary=(
                        f"{decision.capitalize()}d {document.document_type} "
                        f"v{document.version} for opportunity {document.opportunity_id}."
                    ),
                    details={
                        "opportunity_id": document.opportunity_id,
                        "document_type": document.document_type,
                        "version": document.version,
                        "rationale": rationale,
                    },
                )
            )
            session.commit()

    def _prepare(self, opportunity_id: int) -> tuple[dict, dict, bytes]:
        """Load and gate-check the opportunity, and load the master résumé bytes."""
        with self.database.session() as session:
            opportunity = session.execute(
                select(Opportunity.__table__).where(Opportunity.id == opportunity_id)
            ).mappings().first()
            if opportunity is None:
                raise ValueError(f"opportunity not found: {opportunity_id}")
            if opportunity["lifecycle_status"] != "preparing":
                raise ValueError(
                    "documents can only be generated for opportunities with "
                    "lifecycle_status 'preparing' (request preparation first)"
                )
            opportunity_dict = dict(opportunity)

        master = self.resume_service.get_current_master()
        if master is None:
            raise ValueError("import a master résumé before generating application documents")
        resume_bytes = Path(master["storage_path"]).read_bytes()
        return opportunity_dict, master, resume_bytes

    def _latest_successful_scoring(self, opportunity_id: int) -> dict[str, Any] | None:
        with self.database.session() as session:
            run = session.execute(
                select(ScoringRun)
                .where(
                    ScoringRun.opportunity_id == opportunity_id,
                    ScoringRun.status == "succeeded",
                )
                .order_by(ScoringRun.id.desc())
            ).scalars().first()
            if run is None:
                return None
            components = session.execute(
                select(
                    ScoreComponent.component_code,
                    ScoreComponent.score,
                    ScoreComponent.weight,
                    ScoreComponent.explanation,
                ).where(ScoreComponent.scoring_run_id == run.id)
            ).mappings().all()
            return {
                "overall_score": run.overall_score,
                "confidence": run.confidence,
                "fit_summary": run.fit_summary,
                "concerns": run.concerns,
                "components": [
                    {
                        "code": c["component_code"],
                        "score": c["score"],
                        "weight": c["weight"],
                        "explanation": c["explanation"],
                    }
                    for c in components
                ],
            }

    def _run_provider(
        self,
        document_type: str,
        opportunity_id: int,
        call: Callable[[], DocumentGenerationResult],
    ) -> DocumentGenerationResult:
        try:
            return call()
        except Exception as exc:
            with self.database.session() as session:
                AuditService(session).record(
                    AuditEvent(
                        event_type="document_generation_failed",
                        actor_type="scott",
                        entity_type="opportunity",
                        entity_id=opportunity_id,
                        constitution_version=self.constitution.version,
                        summary=f"{document_type} generation failed: {exc}",
                        details={"document_type": document_type, "error": str(exc)},
                    )
                )
            raise

    def _persist(
        self,
        document_type: str,
        opportunity_id: int,
        master: dict,
        result: DocumentGenerationResult,
    ) -> dict:
        content_hash = hashlib.sha256(result.content.encode("utf-8")).hexdigest()
        self.storage_path.mkdir(parents=True, exist_ok=True)
        destination = self.storage_path / f"{content_hash}.txt"
        destination.write_text(result.content, encoding="utf-8")

        status = "validation_failed" if result.unsupported_claims else "ready_for_review"

        with self.database.session() as session:
            previous_version = session.execute(
                select(GeneratedDocument.version)
                .where(
                    GeneratedDocument.opportunity_id == opportunity_id,
                    GeneratedDocument.document_type == document_type,
                )
                .order_by(GeneratedDocument.version.desc())
            ).scalars().first()
            next_version = (previous_version + 1) if previous_version is not None else 1

            row = GeneratedDocument(
                opportunity_id=opportunity_id,
                resume_source_id=master["id"],
                document_type=document_type,
                version=next_version,
                status=status,
                storage_path=str(destination),
                content_hash=content_hash,
                provider=self.provider.provider_name,
                model=self.provider.model_name,
                prompt_version=self.provider.prompt_version,
                unsupported_claims_json=json.dumps(result.unsupported_claims),
                generated_at=now_iso(),
            )
            session.add(row)
            session.flush()
            AuditService(session).record(
                AuditEvent(
                    event_type="document_generated",
                    actor_type="scott",
                    entity_type="opportunity",
                    entity_id=opportunity_id,
                    constitution_version=self.constitution.version,
                    summary=(
                        f"Generated {document_type} v{next_version} "
                        f"(status={status}, unsupported_claims={len(result.unsupported_claims)})."
                    ),
                    details={
                        "document_id": row.id,
                        "document_type": document_type,
                        "version": next_version,
                        "status": status,
                        "unsupported_claims": result.unsupported_claims,
                    },
                )
            )
            session.commit()

            return {
                "document_id": row.id,
                "version": next_version,
                "status": status,
                "unsupported_claims": result.unsupported_claims,
            }
