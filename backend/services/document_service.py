"""Tailored-résumé generation, grounded in the master résumé."""

import hashlib
import json
from pathlib import Path

from sqlalchemy import select

from backend.database import Database
from backend.db.models import GeneratedDocument, Opportunity
from backend.documents.base import DocumentGenerationProvider
from backend.services.audit_service import AuditEvent, AuditService
from backend.services.constitution_service import Constitution
from backend.services.resume_service import ResumeService
from backend.timeutil import now_iso

_DOCUMENT_TYPE = "tailored_resume"


class DocumentService:
    """Generate a tailored résumé draft for one opportunity.

    Generation requires `lifecycle_status == "preparing"` — Scott's own
    `request_preparation` review decision — not just "eligible" or
    "scored", matching the constitution's "notify, then wait for explicit
    approval" pipeline. A provider failure records an audit event but
    writes no `generated_documents` row, since the schema's `status`
    check constraint has no failure state (`OE-ADR-020`).
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
        with self.database.session() as session:
            opportunity = session.execute(
                select(Opportunity.__table__).where(Opportunity.id == opportunity_id)
            ).mappings().first()
            if opportunity is None:
                raise ValueError(f"opportunity not found: {opportunity_id}")
            if opportunity["lifecycle_status"] != "preparing":
                raise ValueError(
                    "tailored résumés can only be generated for opportunities with "
                    "lifecycle_status 'preparing' (request preparation first)"
                )
            opportunity_dict = dict(opportunity)

        master = self.resume_service.get_current_master()
        if master is None:
            raise ValueError("import a master résumé before generating tailored documents")
        resume_bytes = Path(master["storage_path"]).read_bytes()

        try:
            result = self.provider.generate_tailored_resume(
                opportunity_dict, master, resume_bytes, self.constitution
            )
        except Exception as exc:
            with self.database.session() as session:
                AuditService(session).record(
                    AuditEvent(
                        event_type="document_generation_failed",
                        actor_type="scott",
                        entity_type="opportunity",
                        entity_id=opportunity_id,
                        constitution_version=self.constitution.version,
                        summary=f"Tailored résumé generation failed: {exc}",
                        details={"document_type": _DOCUMENT_TYPE, "error": str(exc)},
                    )
                )
            raise

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
                    GeneratedDocument.document_type == _DOCUMENT_TYPE,
                )
                .order_by(GeneratedDocument.version.desc())
            ).scalars().first()
            next_version = (previous_version + 1) if previous_version is not None else 1

            row = GeneratedDocument(
                opportunity_id=opportunity_id,
                resume_source_id=master["id"],
                document_type=_DOCUMENT_TYPE,
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
                        f"Generated tailored résumé v{next_version} "
                        f"(status={status}, unsupported_claims={len(result.unsupported_claims)})."
                    ),
                    details={
                        "document_id": row.id,
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
