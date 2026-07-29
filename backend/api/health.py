"""Health and readiness endpoints."""

from fastapi import APIRouter, Request
from pydantic import BaseModel


router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class ReadinessResponse(HealthResponse):
    database: str
    constitution_version: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Return process-level health without touching dependencies."""
    return HealthResponse(
        status="ok",
        service="OpportunityEngine",
        version="0.1.0",
    )


@router.get("/ready", response_model=ReadinessResponse)
def ready(request: Request) -> ReadinessResponse:
    """Return readiness only when policy and persistence are available."""
    database = request.app.state.database
    constitution = request.app.state.constitution
    database_status = "ok" if database.ping() else "unavailable"
    return ReadinessResponse(
        status="ready" if database_status == "ok" else "not_ready",
        service="OpportunityEngine",
        version="0.1.0",
        database=database_status,
        constitution_version=constitution.version,
    )

