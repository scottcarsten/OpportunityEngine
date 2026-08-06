"""Tests for approval receipts on restricted actions (OE-ADR-032)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from backend.app import create_app
from backend.config import Settings
from backend.database import Database
from backend.db.models import ApprovalRequest, AuditEventRecord
from backend.services.approval_service import ApprovalService
from backend.services.constitution_service import load_constitution


def _service(tmp_path: Path) -> tuple[ApprovalService, Database]:
    database = Database(database_path=tmp_path / "opportunity_engine.db")
    database.initialize()
    constitution = load_constitution(Path("config/constitution.json"))
    return ApprovalService(database, constitution), database


def test_request_approval_creates_pending_row_and_audits(tmp_path: Path) -> None:
    service, database = _service(tmp_path)

    request_id = service.request_approval(
        "email", "hiring@acme.example", "Send follow-up email to Acme Corp recruiter."
    )

    with database.session() as session:
        request = session.get(ApprovalRequest, request_id)
        assert request.status == "pending"
        assert request.action_type == "email"
        assert request.target == "hiring@acme.example"

        audit_events = session.execute(
            select(AuditEventRecord).where(AuditEventRecord.event_type == "approval_requested")
        ).scalars().all()
    assert len(audit_events) == 1
    assert audit_events[0].entity_id == request_id


def test_request_approval_rejects_invalid_action_type(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)

    with pytest.raises(ValueError, match="unsupported action_type"):
        service.request_approval("bogus", "target", "scope")


def test_approve_flips_status_and_audits(tmp_path: Path) -> None:
    service, database = _service(tmp_path)
    request_id = service.request_approval("application", "Acme Corp", "Submit application.")

    service.approve(request_id, resolution_note="Looks good.")

    with database.session() as session:
        request = session.get(ApprovalRequest, request_id)
        assert request.status == "approved"
        assert request.resolved_by == "scott"
        assert request.resolved_at is not None
        assert request.resolution_note == "Looks good."

        audit_events = session.execute(
            select(AuditEventRecord).where(AuditEventRecord.event_type == "approval_decision")
        ).scalars().all()
    assert len(audit_events) == 1


def test_reject_flips_status_and_audits(tmp_path: Path) -> None:
    service, database = _service(tmp_path)
    request_id = service.request_approval("contract", "Acme Corp", "Sign contract.")

    service.reject(request_id, resolution_note="Not yet.")

    with database.session() as session:
        request = session.get(ApprovalRequest, request_id)
        assert request.status == "rejected"
        assert request.resolved_by == "scott"


def test_approving_a_resolved_request_raises(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    request_id = service.request_approval("email", "target", "scope")
    service.approve(request_id)

    with pytest.raises(ValueError, match="not pending"):
        service.approve(request_id)

    with pytest.raises(ValueError, match="not pending"):
        service.reject(request_id)


def test_resolving_an_unknown_request_raises(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)

    with pytest.raises(ValueError, match="not found"):
        service.approve(999)


def test_expire_stale_requests_expires_a_pending_request_past_its_expiry(
    tmp_path: Path,
) -> None:
    service, database = _service(tmp_path)
    request_id = service.request_approval("email", "target", "scope", expires_in_days=1)
    with database.session() as session:
        session.execute(
            update(ApprovalRequest)
            .where(ApprovalRequest.id == request_id)
            .values(expires_at="2000-01-01T00:00:00.000000Z")
        )
        session.commit()

    expired_ids = service.expire_stale_requests()

    assert request_id in expired_ids
    with database.session() as session:
        request = session.get(ApprovalRequest, request_id)
        assert request.status == "expired"
        audit_events = session.execute(
            select(AuditEventRecord).where(AuditEventRecord.event_type == "approval_expired")
        ).scalars().all()
    assert len(audit_events) == 1


def test_expire_stale_requests_leaves_an_already_resolved_request_alone(
    tmp_path: Path,
) -> None:
    service, database = _service(tmp_path)
    request_id = service.request_approval("email", "target", "scope", expires_in_days=1)
    service.approve(request_id)
    with database.session() as session:
        session.execute(
            update(ApprovalRequest)
            .where(ApprovalRequest.id == request_id)
            .values(expires_at="2000-01-01T00:00:00.000000Z")
        )
        session.commit()

    expired_ids = service.expire_stale_requests()

    assert request_id not in expired_ids
    with database.session() as session:
        request = session.get(ApprovalRequest, request_id)
        assert request.status == "approved"


def test_expire_stale_requests_never_expires_a_request_with_no_expiry(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    service.request_approval("email", "target", "scope")

    expired_ids = service.expire_stale_requests()

    assert expired_ids == []


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = Settings(
        database_path=tmp_path / "opportunity_engine.db",
        constitution_path=Path("config/constitution.json"),
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_approvals_page_shows_empty_state(client: TestClient) -> None:
    response = client.get("/approvals")

    assert response.status_code == 200
    assert "No approval requests yet" in response.text


def test_approvals_page_lists_a_pending_request(
    client: TestClient, tmp_path: Path
) -> None:
    service = ApprovalService(
        client.app.state.database, client.app.state.constitution
    )
    service.request_approval("email", "hiring@acme.example", "Send follow-up email.")

    response = client.get("/approvals")

    assert "hiring@acme.example" in response.text
    assert "Pending" in response.text


def test_approve_route_flips_status(client: TestClient) -> None:
    service = ApprovalService(
        client.app.state.database, client.app.state.constitution
    )
    request_id = service.request_approval("email", "target", "scope")

    response = client.post(
        f"/approvals/{request_id}/approve",
        data={"resolution_note": "Go ahead."},
        follow_redirects=False,
    )

    assert response.status_code == 303
    detail = client.get("/approvals")
    assert "Approved" in detail.text
    assert "Go ahead." in detail.text


def test_reject_route_flips_status(client: TestClient) -> None:
    service = ApprovalService(
        client.app.state.database, client.app.state.constitution
    )
    request_id = service.request_approval("email", "target", "scope")

    response = client.post(f"/approvals/{request_id}/reject", data={}, follow_redirects=False)

    assert response.status_code == 303
    detail = client.get("/approvals")
    assert "Rejected" in detail.text


def test_approving_a_non_pending_request_returns_422(client: TestClient) -> None:
    service = ApprovalService(
        client.app.state.database, client.app.state.constitution
    )
    request_id = service.request_approval("email", "target", "scope")
    service.approve(request_id)

    response = client.post(f"/approvals/{request_id}/approve", data={}, follow_redirects=False)

    assert response.status_code == 422
