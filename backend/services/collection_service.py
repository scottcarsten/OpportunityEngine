"""Orchestrate one source adapter's fetch/normalize/ingest run."""

from uuid import uuid4

from sqlalchemy import select, update

from backend.adapters.base import SourceAdapter
from backend.database import Database
from backend.db.models import CollectionRun, SourceRecord
from backend.services.constitution_service import Constitution
from backend.services.opportunity_service import OpportunityService
from backend.timeutil import now_iso


class CollectionService:
    """Run a source adapter and persist its evidence and outcomes."""

    def __init__(self, database: Database, constitution: Constitution) -> None:
        self.database = database
        self.opportunity_service = OpportunityService(database, constitution)

    def run(self, adapter: SourceAdapter) -> dict:
        """Fetch, normalize, and ingest one adapter's current listings.

        Idempotent: a listing already seen from this source (same
        `external_id`) is skipped after bumping `last_seen_at`, relying on
        the schema's `uq_source_records_source_external` constraint as the
        source of truth for "have I seen this before."
        """
        with self.database.session() as session:
            source_id = self.opportunity_service.ensure_source(
                session, adapter.source_name, adapter.source_type, adapter.base_url
            )
            run_row = CollectionRun(
                source_id=source_id,
                status="running",
                correlation_id=str(uuid4()),
                started_at=now_iso(),
            )
            session.add(run_row)
            session.flush()
            run_id = run_row.id
            session.commit()

        records_seen = 0
        records_created = 0
        records_updated = 0
        error_summary: str | None = None
        status = "succeeded"

        try:
            raw_records = adapter.fetch()
            for raw in raw_records:
                records_seen += 1
                created = self._ingest_one(
                    source_id=source_id, run_id=run_id, raw=raw, adapter=adapter
                )
                if created:
                    records_created += 1
                else:
                    records_updated += 1
        except Exception as exc:  # noqa: BLE001 - recorded on the run, not swallowed
            status = "failed"
            error_summary = str(exc)

        with self.database.session() as session:
            session.execute(
                update(CollectionRun)
                .where(CollectionRun.id == run_id)
                .values(
                    status=status,
                    completed_at=now_iso(),
                    records_seen=records_seen,
                    records_created=records_created,
                    records_updated=records_updated,
                    error_summary=error_summary,
                )
            )
            session.commit()

        return {
            "run_id": run_id,
            "status": status,
            "records_seen": records_seen,
            "records_created": records_created,
            "records_updated": records_updated,
            "error_summary": error_summary,
        }

    def _ingest_one(self, *, source_id: int, run_id: int, raw, adapter) -> bool:
        """Ingest one raw record; return True only if it created a new opportunity."""
        with self.database.session() as session:
            already_seen_id = session.execute(
                select(SourceRecord.id).where(
                    SourceRecord.source_id == source_id,
                    SourceRecord.external_id == raw.external_id,
                )
            ).scalar_one_or_none()
            if already_seen_id is not None:
                session.execute(
                    update(SourceRecord)
                    .where(SourceRecord.id == already_seen_id)
                    .values(last_seen_at=now_iso())
                )
                session.commit()
                return False

            supplied = adapter.normalize(raw)
            _, created = self.opportunity_service.ingest_collected(
                session,
                supplied,
                source_id=source_id,
                external_id=raw.external_id,
                collection_run_id=run_id,
            )
            return created
