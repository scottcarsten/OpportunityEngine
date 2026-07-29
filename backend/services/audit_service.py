"""Append-only audit-event writer."""

import json
import sqlite3
from dataclasses import dataclass
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class AuditEvent:
    event_type: str
    actor_type: str
    summary: str
    entity_type: str | None = None
    entity_id: int | None = None
    actor_identifier: str | None = None
    constitution_version: str | None = None
    details: dict[str, Any] | None = None
    correlation_id: str | None = None


class AuditService:
    """Persist audit events without update or delete operations."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def record(self, event: AuditEvent) -> int:
        """Append one audit event and return its database identifier."""
        correlation_id = event.correlation_id or str(uuid4())
        cursor = self.connection.execute(
            """
            INSERT INTO audit_events (
                correlation_id,
                event_type,
                actor_type,
                actor_identifier,
                entity_type,
                entity_id,
                constitution_version,
                summary,
                details_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                correlation_id,
                event.event_type,
                event.actor_type,
                event.actor_identifier,
                event.entity_type,
                event.entity_id,
                event.constitution_version,
                event.summary,
                json.dumps(event.details) if event.details is not None else None,
            ),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

