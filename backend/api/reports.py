"""Pipeline reporting: volume, quality, and estimated value."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from backend.services.reporting_service import ReportingService

router = APIRouter()
templates = Jinja2Templates(directory=str(Path("templates")))


@router.get("/reports", response_class=HTMLResponse)
def pipeline_report(request: Request) -> HTMLResponse:
    service = ReportingService(database=request.app.state.database)
    return templates.TemplateResponse(
        request=request,
        name="reports.html",
        context={"report": service.build_report()},
    )
