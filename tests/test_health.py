"""FastAPI health endpoint tests."""

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import Settings


def test_health_and_readiness(tmp_path: Path) -> None:
    settings = Settings(
        database_path=tmp_path / "opportunity_engine.db",
        schema_path=Path("database/schema.sql"),
        constitution_path=Path("config/constitution.json"),
    )
    with TestClient(create_app(settings)) as client:
        health = client.get("/health")
        ready = client.get("/ready")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    assert ready.json()["database"] == "ok"

