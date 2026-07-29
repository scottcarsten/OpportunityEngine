"""FastAPI application factory for OpportunityEngine."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI

from backend.api.health import router as health_router
from backend.api.opportunities import router as opportunities_router
from backend.config import Settings, get_settings
from backend.database import Database
from backend.logging_config import configure_logging
from backend.services.constitution_service import Constitution, load_constitution


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the OpportunityEngine application."""
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(resolved_settings.log_level)
        constitution = load_constitution(resolved_settings.constitution_path)
        database = Database(
            database_path=resolved_settings.database_path,
            schema_path=resolved_settings.schema_path,
        )
        database.initialize()

        app.state.settings = resolved_settings
        app.state.constitution = constitution
        app.state.database = database
        yield
        database.close()

    application = FastAPI(
        title="OpportunityEngine",
        version="0.1.0",
        description="Human-controlled opportunity discovery and qualification.",
        lifespan=lifespan,
        docs_url="/docs" if resolved_settings.enable_api_docs else None,
        redoc_url=None,
    )
    application.state.settings = resolved_settings
    application.include_router(health_router)
    application.include_router(opportunities_router)
    return application


app = create_app()
