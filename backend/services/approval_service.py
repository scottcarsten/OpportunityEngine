"""Explicit approval receipts for restricted actions (OE-ADR-032).

`approval_requests` mirrors `config/constitution.json`'s
`human_approval_required` list: nothing here executes a restricted
action itself - it's the audited gate a future feature would call
before ever applying, emailing, signing a contract, verifying
identity, or committing funds on Scott's behalf.
"""

from typing import Any

from sqlalchemy import select, update

from backend.database import Database
from backend.db.models import ApprovalRequest
from backend.services.audit_service import AuditEvent, AuditService
from backend.services.constitution_service import Constitution
from backend.timeutil import add_days_iso, now_iso

_ACTION_TYPES = (
    "application",
    "email",
    "external_message",
    "contract",
    "identity_verification",
    "financial_commitment",
)


class ApprovalService:
    """Request, resolve, and expire approval receipts for restricted actions."""

    def __init__(self, database: Database, constitution: Constitution) -> None:
        self.database = database
        self.constitution = constitution

    def request_approval(
        self,
        action_type: str,
        target: str,
        scope: str,
        requested_by: str = "system",
        opportunity_id: int | None = None,
        generated_document_id: int | None = None,
        expires_in_days: int | None = None,
    ) -> int:
        """Create a pending approval request. Returns its id.

        `scope` should describe exactly what's being approved - approval
        for one action and target is never approval for anything else
        (ARCHITECTURE.md §5.6).
        """
        if action_type not in _ACTION_TYPES:
            raise ValueError(f"unsupported action_type: {action_type}")

        with self.database.session() as session:
            request = ApprovalRequest(
                opportunity_id=opportunity_id,
                generated_document_id=generated_document_id,
                action_type=action_type,
                target=target,
                scope=scope,
                requested_by=requested_by,
                expires_at=add_days_iso(expires_in_days) if expires_in_days else None,
            )
            session.add(request)
            session.flush()
            request_id = request.id
            AuditService(session).record(
                AuditEvent(
                    event_type="approval_requested",
                    actor_type="system",
                    entity_type="approval_request",
                    entity_id=request_id,
                    constitution_version=self.constitution.version,
                    summary=f"Requested approval for {action_type} targeting '{target}'.",
                )
            )
            session.commit()
            return request_id

    def approve(
        self, approval_request_id: int, resolution_note: str | None = None, resolved_by: str = "scott"
    ) -> None:
        self._resolve(approval_request_id, "approved", resolution_note, resolved_by)

    def reject(
        self, approval_request_id: int, resolution_note: str | None = None, resolved_by: str = "scott"
    ) -> None:
        self._resolve(approval_request_id, "rejected", resolution_note, resolved_by)

    def _resolve(
        self,
        approval_request_id: int,
        new_status: str,
        resolution_note: str | None,
        resolved_by: str,
    ) -> None:
        with self.database.session() as session:
            request = session.execute(
                select(ApprovalRequest).where(ApprovalRequest.id == approval_request_id)
            ).scalar_one_or_none()
            if request is None:
                raise ValueError(f"approval request not found: {approval_request_id}")
            if request.status != "pending":
                raise ValueError(
                    f"approval request {approval_request_id} is not pending "
                    f"(status={request.status})"
                )

            request.status = new_status
            request.resolved_by = resolved_by
            request.resolved_at = now_iso()
            request.resolution_note = resolution_note
            AuditService(session).record(
                AuditEvent(
                    event_type="approval_decision",
                    actor_type="scott",
                    entity_type="approval_request",
                    entity_id=approval_request_id,
                    constitution_version=self.constitution.version,
                    summary=f"Approval request {new_status}.",
                )
            )
            session.commit()

    def expire_stale_requests(self) -> list[int]:
        """Move `pending` requests whose `expires_at` has passed to `expired`.

        Only ever touches `pending` rows - an already-resolved request
        is never overridden, same boundary as
        `OpportunityService.expire_stale_opportunities`.
        """
        now = now_iso()
        with self.database.session() as session:
            candidate_ids = session.execute(
                select(ApprovalRequest.id).where(
                    ApprovalRequest.status == "pending",
                    ApprovalRequest.expires_at.is_not(None),
                    ApprovalRequest.expires_at < now,
                )
            ).scalars().all()
            for request_id in candidate_ids:
                session.execute(
                    update(ApprovalRequest)
                    .where(ApprovalRequest.id == request_id)
                    .values(status="expired")
                )
                AuditService(session).record(
                    AuditEvent(
                        event_type="approval_expired",
                        actor_type="system",
                        entity_type="approval_request",
                        entity_id=request_id,
                        constitution_version=self.constitution.version,
                        summary="Approval request expired without a decision.",
                    )
                )
            session.commit()
            return list(candidate_ids)

    def list_requests(self) -> list[dict[str, Any]]:
        with self.database.session() as session:
            rows = session.execute(
                select(ApprovalRequest.__table__).order_by(ApprovalRequest.requested_at.desc())
            ).mappings().all()
        return [dict(row) for row in rows]
