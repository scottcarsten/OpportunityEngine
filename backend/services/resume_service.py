"""Master résumé import and versioning (v0.2, read-only source material)."""

import hashlib
from pathlib import Path
from typing import Any

from sqlalchemy import select

from backend.database import Database
from backend.db.models import ResumeSource
from backend.services.audit_service import AuditEvent, AuditService
from backend.services.constitution_service import Constitution

_ALLOWED_MIME_TYPES = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/plain": ".txt",
}
_MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024


class ResumeService:
    """Import and version the master résumé as immutable source material.

    Per the DB triggers on `resume_sources`, a row with `is_master=1` can
    never be updated or deleted — there is no "unmark the old one as
    current" step. "Current" is derived (highest version), not stored, and
    no method here ever attempts an update or delete. See `OE-ADR-019`.
    """

    def __init__(
        self, database: Database, constitution: Constitution, storage_path: Path
    ) -> None:
        self.database = database
        self.constitution = constitution
        self.storage_path = storage_path

    def import_master_resume(
        self, file_name: str, content: bytes, mime_type: str, notes: str | None = None
    ) -> dict[str, Any]:
        if mime_type not in _ALLOWED_MIME_TYPES:
            raise ValueError(f"unsupported résumé file type: {mime_type}")
        if not content:
            raise ValueError("résumé file is empty")
        if len(content) > _MAX_FILE_SIZE_BYTES:
            raise ValueError("résumé file exceeds the 10 MB size limit")

        content_hash = hashlib.sha256(content).hexdigest()

        with self.database.session() as session:
            existing = session.execute(
                select(ResumeSource).where(ResumeSource.content_hash == content_hash)
            ).scalar_one_or_none()
            if existing is not None:
                return self._to_dict(existing)

            previous = session.execute(
                select(ResumeSource).order_by(ResumeSource.version.desc())
            ).scalars().first()
            next_version = (previous.version + 1) if previous is not None else 1

            # Path is derived only from the content hash and the validated
            # mime type's extension — never the untrusted supplied filename.
            # That is what actually prevents path traversal, not validating
            # file_name (ARCHITECTURE.md §10).
            self.storage_path.mkdir(parents=True, exist_ok=True)
            destination = self.storage_path / f"{content_hash}{_ALLOWED_MIME_TYPES[mime_type]}"
            destination.write_bytes(content)

            try:
                row = ResumeSource(
                    version=next_version,
                    file_name=file_name,
                    storage_path=str(destination),
                    content_hash=content_hash,
                    mime_type=mime_type,
                    supersedes_id=previous.id if previous is not None else None,
                    notes=notes,
                )
                session.add(row)
                session.flush()
                AuditService(session).record(
                    AuditEvent(
                        event_type="resume_imported",
                        actor_type="scott",
                        entity_type="resume_source",
                        entity_id=row.id,
                        constitution_version=self.constitution.version,
                        summary=f"Imported master résumé version {next_version}: {file_name}.",
                        details={
                            "version": next_version,
                            "file_name": file_name,
                            "notes": notes,
                        },
                    )
                )
            except Exception:
                session.rollback()
                destination.unlink(missing_ok=True)
                raise

            return self._to_dict(row)

    def get_current_master(self) -> dict[str, Any] | None:
        """Return the highest-version `is_master=1` row, if any."""
        with self.database.session() as session:
            row = session.execute(
                select(ResumeSource)
                .where(ResumeSource.is_master == 1)
                .order_by(ResumeSource.version.desc())
            ).scalars().first()
            return self._to_dict(row) if row is not None else None

    def list_resume_history(self) -> list[dict[str, Any]]:
        """Return every master résumé version, newest first."""
        with self.database.session() as session:
            rows = session.execute(
                select(ResumeSource)
                .where(ResumeSource.is_master == 1)
                .order_by(ResumeSource.version.desc())
            ).scalars().all()
            return [self._to_dict(row) for row in rows]

    @staticmethod
    def _to_dict(row: ResumeSource) -> dict[str, Any]:
        return {
            "id": row.id,
            "version": row.version,
            "file_name": row.file_name,
            "storage_path": row.storage_path,
            "content_hash": row.content_hash,
            "mime_type": row.mime_type,
            "imported_by": row.imported_by,
            "imported_at": row.imported_at,
            "supersedes_id": row.supersedes_id,
            "notes": row.notes,
        }
