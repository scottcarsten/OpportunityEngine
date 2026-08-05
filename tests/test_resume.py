"""Master résumé import and versioning tests (v0.2 first slice)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from backend.app import create_app
from backend.config import Settings
from backend.database import Database
from backend.db.models import AuditEventRecord, ResumeSource
from backend.services.constitution_service import Constitution, load_constitution
from backend.services.resume_service import ResumeService


def _resume_service(tmp_path: Path) -> tuple[ResumeService, Database, Constitution]:
    database = Database(database_path=tmp_path / "opportunity_engine.db")
    database.initialize()
    constitution = load_constitution(Path("config/constitution.json"))
    service = ResumeService(database, constitution, storage_path=tmp_path / "resumes")
    return service, database, constitution


def test_first_import_creates_version_one(tmp_path: Path) -> None:
    service, database, _ = _resume_service(tmp_path)

    result = service.import_master_resume("resume.txt", b"Scott Carsten's resume.", "text/plain")

    assert result["version"] == 1
    assert result["supersedes_id"] is None
    assert Path(result["storage_path"]).is_file()

    with database.session() as session:
        events = session.execute(
            select(AuditEventRecord).where(AuditEventRecord.event_type == "resume_imported")
        ).scalars().all()
    assert len(events) == 1
    assert events[0].entity_id == result["id"]


def test_second_different_import_creates_version_two(tmp_path: Path) -> None:
    service, _, _ = _resume_service(tmp_path)
    first = service.import_master_resume("resume.txt", b"Version one content.", "text/plain")
    second = service.import_master_resume("resume-v2.txt", b"Version two content.", "text/plain")

    assert second["version"] == 2
    assert second["supersedes_id"] == first["id"]
    assert service.get_current_master()["version"] == 2
    assert len(service.list_resume_history()) == 2


def test_reimporting_identical_content_is_a_no_op(tmp_path: Path) -> None:
    service, _, _ = _resume_service(tmp_path)
    first = service.import_master_resume("resume.txt", b"Same content.", "text/plain")
    second = service.import_master_resume("resume-copy.txt", b"Same content.", "text/plain")

    assert first["id"] == second["id"]
    assert first["version"] == second["version"]
    assert len(service.list_resume_history()) == 1


def test_rejected_mime_type_raises_without_touching_disk_or_db(tmp_path: Path) -> None:
    service, database, _ = _resume_service(tmp_path)

    with pytest.raises(ValueError, match="unsupported"):
        service.import_master_resume(
            "resume.exe", b"binary content", "application/x-executable"
        )

    assert service.get_current_master() is None
    assert not (tmp_path / "resumes").exists() or not any((tmp_path / "resumes").iterdir())


def test_oversized_file_raises(tmp_path: Path) -> None:
    service, _, _ = _resume_service(tmp_path)

    with pytest.raises(ValueError, match="exceeds"):
        service.import_master_resume(
            "resume.txt", b"x" * (10 * 1024 * 1024 + 1), "text/plain"
        )


def test_master_resume_row_is_immutable_at_the_db_level(tmp_path: Path) -> None:
    service, database, _ = _resume_service(tmp_path)
    result = service.import_master_resume("resume.txt", b"Immutable content.", "text/plain")

    with database.session() as session:
        with pytest.raises(IntegrityError, match="immutable"):
            session.execute(
                update(ResumeSource)
                .where(ResumeSource.id == result["id"])
                .values(notes="sneaky edit")
            )

    with database.session() as session:
        with pytest.raises(IntegrityError, match="cannot be deleted"):
            session.execute(delete(ResumeSource).where(ResumeSource.id == result["id"]))


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = Settings(
        database_path=tmp_path / "opportunity_engine.db",
        constitution_path=Path("config/constitution.json"),
        resume_storage_path=tmp_path / "resumes",
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_resume_route_shows_uploaded_version(client: TestClient) -> None:
    response = client.post(
        "/resume",
        files={"file": ("resume.txt", b"Route-uploaded resume content.", "text/plain")},
        data={"notes": "First upload"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    page = client.get("/resume")
    assert "Version 1" in page.text or "1" in page.text
    assert "resume.txt" in page.text
    assert "First upload" in page.text


def test_resume_route_rejects_bad_file_type(client: TestClient) -> None:
    response = client.post(
        "/resume",
        files={"file": ("resume.exe", b"nope", "application/x-executable")},
        follow_redirects=False,
    )
    assert response.status_code == 422
