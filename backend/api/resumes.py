"""Master résumé import and version history."""

from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from backend.services.resume_service import ResumeService

router = APIRouter()
templates = Jinja2Templates(directory=str(Path("templates")))


def _service(request: Request) -> ResumeService:
    return ResumeService(
        database=request.app.state.database,
        constitution=request.app.state.constitution,
        storage_path=request.app.state.settings.resume_storage_path,
    )


@router.get("/resume", response_class=HTMLResponse)
def resume_page(request: Request) -> HTMLResponse:
    service = _service(request)
    return templates.TemplateResponse(
        request=request,
        name="resume.html",
        context={
            "current": service.get_current_master(),
            "history": service.list_resume_history(),
        },
    )


@router.post("/resume")
async def upload_resume(
    request: Request, file: UploadFile = File(...), notes: str = Form("")
) -> RedirectResponse:
    content = await file.read()
    try:
        _service(request).import_master_resume(
            file_name=file.filename or "resume",
            content=content,
            mime_type=file.content_type or "",
            notes=notes.strip() or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return RedirectResponse(url="/resume", status_code=303)
