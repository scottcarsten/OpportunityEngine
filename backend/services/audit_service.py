"""Append-only audit-event writer."""

import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from backend.db.models import AuditEventRecord


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

    def __init__(self, session: Session) -> None:
        self.session = session

    def record(self, event: AuditEvent) -> int:
        """Append one audit event and return its database identifier."""
        row = AuditEventRecord(
            correlation_id=event.correlation_id or str(uuid4()),
            event_type=event.event_type,
            actor_type=event.actor_type,
            actor_identifier=event.actor_identifier,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            constitution_version=event.constitution_version,
            summary=event.summary,
            details_json=json.dumps(event.details) if event.details is not None else None,
        )
        self.session.add(row)
        self.session.commit()
        return int(row.id)
