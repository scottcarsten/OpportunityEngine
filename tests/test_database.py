"""Database initialization and guardrail tests."""

from pathlib import Path

import pytest
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from backend.database import Database
from backend.db.models import AuditEventRecord


def test_schema_initializes_and_audit_is_append_only(tmp_path: Path) -> None:
    database = Database(database_path=tmp_path / "opportunity_engine.db")
    database.initialize()
    assert database.ping() is True

    with database.session() as session:
        event = AuditEventRecord(
            correlation_id="test-correlation",
            event_type="test",
            actor_type="system",
            summary="test event",
        )
        session.add(event)
        session.commit()
        event_id = event.id

        with pytest.raises(IntegrityError, match="append-only"):
            session.execute(
                update(AuditEventRecord)
                .where(AuditEventRecord.id == event_id)
                .values(summary="changed")
            )
    database.close()
