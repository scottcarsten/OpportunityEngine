"""Database initialization and guardrail tests."""

import sqlite3
from pathlib import Path

import pytest

from backend.database import Database


def test_schema_initializes_and_audit_is_append_only(tmp_path: Path) -> None:
    database = Database(
        database_path=tmp_path / "opportunity_engine.db",
        schema_path=Path("database/schema.sql"),
    )
    database.initialize()
    assert database.ping() is True

    connection = database.connection
    cursor = connection.execute(
        """
        INSERT INTO audit_events (
            correlation_id, event_type, actor_type, summary
        )
        VALUES ('test-correlation', 'test', 'system', 'test event')
        """
    )
    connection.commit()

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        connection.execute(
            "UPDATE audit_events SET summary = 'changed' WHERE id = ?",
            (cursor.lastrowid,),
        )
    database.close()

