"""Explicit approval receipts for restricted actions (OE-ADR-032)."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from backend.services.approval_service import ApprovalService

router = APIRouter()
templates = Jinja2Templates(directory=str(Path("templates")))


def _service(request: Request) -> ApprovalService:
    return ApprovalService(
        database=request.app.state.database,
        constitution=request.app.state.constitution,
    )


@router.get("/approvals", response_class=HTMLResponse)
def approvals_page(request: Request) -> HTMLResponse:
    service = _service(request)
    return templates.TemplateResponse(
        request=request,
        name="approvals.html",
        context={"requests": service.list_requests()},
    )


@router.post("/approvals/{approval_request_id}/approve")
async def approve_request(request: Request, approval_request_id: int) -> RedirectResponse:
    service = _service(request)
    form = await request.form()
    try:
        service.approve(
            approval_request_id, resolution_note=str(form.get("resolution_note", "")).strip() or None
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return RedirectResponse(url="/approvals", status_code=303)


@router.post("/approvals/{approval_request_id}/reject")
async def reject_request(request: Request, approval_request_id: int) -> RedirectResponse:
    service = _service(request)
    form = await request.form()
    try:
        service.reject(
            approval_request_id, resolution_note=str(form.get("resolution_note", "")).strip() or None
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return RedirectResponse(url="/approvals", status_code=303)
