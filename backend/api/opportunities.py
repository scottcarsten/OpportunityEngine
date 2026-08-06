"""Server-rendered manual opportunity workflow."""

import re
from pathlib import Path
from typing import Any, Literal, cast

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from backend.documents.cover_letter_render import (
    parse_cover_letter_content,
    render_cover_letter_docx,
    render_cover_letter_pdf,
)
from backend.documents.cover_letter_render import (
    render_plain_text_preview as render_cover_letter_preview,
)
from backend.documents.export import render_docx, render_pdf
from backend.documents.markdown_subset import parse as parse_markdown_subset
from backend.documents.resume_render import (
    parse_resume_content,
    render_plain_text_preview,
    render_resume_docx,
    render_resume_pdf,
)
from backend.models import EngagementType, OpportunityInput, RemoteStatus, TaxType
from backend.profile import load_profile
from backend.services.document_service import DocumentService
from backend.services.opportunity_service import OpportunityService
from backend.services.resume_service import ResumeService
from backend.services.scoring_service import ScoringService


router = APIRouter()
templates = Jinja2Templates(directory=str(Path("templates")))


def _service(request: Request) -> OpportunityService:
    return OpportunityService(
        database=request.app.state.database,
        constitution=request.app.state.constitution,
    )


def _scoring_service(request: Request) -> ScoringService:
    return ScoringService(
        database=request.app.state.database,
        constitution=request.app.state.constitution,
        provider=request.app.state.scoring_provider,
    )


def _document_service(request: Request) -> DocumentService:
    resume_service = ResumeService(
        database=request.app.state.database,
        constitution=request.app.state.constitution,
        storage_path=request.app.state.settings.resume_storage_path,
    )
    return DocumentService(
        database=request.app.state.database,
        constitution=request.app.state.constitution,
        provider=request.app.state.document_provider,
        resume_service=resume_service,
        storage_path=request.app.state.settings.document_storage_path,
    )


@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    status: str | None = None,
    engagement_type: str | None = None,
    tax_type: str | None = None,
) -> HTMLResponse:
    service = _service(request)
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "opportunities": service.list_opportunities(
                lifecycle_status=status,
                engagement_type=engagement_type,
                tax_type=tax_type,
            ),
            "needs_review_count": service.count_pending_review(),
            "current_status": status,
            "current_engagement_type": engagement_type,
            "current_tax_type": tax_type,
        },
    )


@router.get("/opportunities/new", response_class=HTMLResponse)
def new_opportunity(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="new_opportunity.html",
        context={},
    )


@router.post("/opportunities")
async def create_opportunity(request: Request) -> RedirectResponse:
    form = await request.form()
    try:
        supplied = OpportunityInput(
            title=str(form.get("title", "")),
            organization_name=str(form.get("organization_name", "")),
            description=str(form.get("description", "")),
            source_url=str(form.get("source_url", "")),
            location_text=str(form.get("location_text", "")),
            remote_status=cast(
                RemoteStatus,
                _choice(str(form.get("remote_status", "unknown")),
                        {"remote", "hybrid", "onsite", "unknown"}),
            ),
            engagement_type=cast(
                EngagementType,
                _choice(str(form.get("engagement_type", "unknown")), {
                    "contract", "consulting", "project", "part_time",
                    "full_time", "temporary", "unknown",
                }),
            ),
            tax_type=cast(
                TaxType,
                _choice(str(form.get("tax_type", "unknown")),
                        {"1099", "w2", "corp_to_corp", "unknown"}),
            ),
            schedule_text=str(form.get("schedule_text", "")),
            compensation_min=_optional_float(form.get("compensation_min")),
            compensation_max=_optional_float(form.get("compensation_max")),
            compensation_period=_choice(
                str(form.get("compensation_period", "unknown")),
                {"hour", "day", "week", "month", "year", "fixed", "unknown"},
            ),
            requires_travel=_optional_bool(form.get("requires_travel")),
            requires_relocation=_optional_bool(form.get("requires_relocation")),
            requires_clearance=_optional_bool(form.get("requires_clearance")),
            replaces_full_time_work=_optional_bool(
                form.get("replaces_full_time_work")
            ),
        )
        opportunity_id, created = _service(request).create_manual(supplied)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    duplicate = "0" if created else "1"
    return RedirectResponse(
        url=f"/opportunities/{opportunity_id}?duplicate={duplicate}",
        status_code=303,
    )


@router.get("/opportunities/{opportunity_id}", response_class=HTMLResponse)
def opportunity_detail(
    request: Request, opportunity_id: int, duplicate: int = 0
) -> HTMLResponse:
    service = _service(request)
    opportunity = service.get_opportunity(opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    service.mark_notifications_sent(opportunity_id)

    for document in opportunity["generated_documents"]["tailored_resume"]:
        structured = parse_resume_content(document["content"])
        if structured is not None:
            document["content"] = render_plain_text_preview(structured)

    cover_letters = opportunity["generated_documents"]["cover_letter"]
    if cover_letters:
        profile = load_profile(request.app.state.settings.profile_path)
        for document in cover_letters:
            letter = parse_cover_letter_content(document["content"])
            if letter is not None:
                document["content"] = render_cover_letter_preview(letter, profile, opportunity)

    return templates.TemplateResponse(
        request=request,
        name="opportunity_detail.html",
        context={"opportunity": opportunity, "duplicate": duplicate == 1},
    )


@router.post("/opportunities/{opportunity_id}/override")
async def override_opportunity(
    request: Request, opportunity_id: int
) -> RedirectResponse:
    service = _service(request)
    if service.get_opportunity(opportunity_id) is None:
        raise HTTPException(status_code=404, detail="opportunity not found")

    form = await request.form()
    try:
        new_status = cast(
            Literal["eligible", "ineligible"],
            _choice(str(form.get("new_status", "")), {"eligible", "ineligible"}),
        )
        service.override_lifecycle_status(
            opportunity_id, new_status, str(form.get("rationale", ""))
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return RedirectResponse(url=f"/opportunities/{opportunity_id}", status_code=303)


@router.post("/opportunities/{opportunity_id}/review")
async def review_opportunity(request: Request, opportunity_id: int) -> RedirectResponse:
    service = _service(request)
    if service.get_opportunity(opportunity_id) is None:
        raise HTTPException(status_code=404, detail="opportunity not found")

    form = await request.form()
    try:
        defer_remind_days = form.get("defer_remind_days")
        if defer_remind_days is not None:
            decision: Literal[
                "shortlist", "reject", "defer", "request_preparation", "reopen"
            ] = "defer"
            remind_days = int(str(defer_remind_days)) if str(defer_remind_days).strip() else None
        else:
            decision = cast(
                Literal["shortlist", "reject", "defer", "request_preparation", "reopen"],
                _choice(
                    str(form.get("decision", "")),
                    {"shortlist", "reject", "defer", "request_preparation", "reopen"},
                ),
            )
            remind_days = None
        rationale = str(form.get("rationale", "")).strip() or None
        service.record_review_decision(
            opportunity_id, decision, rationale, remind_days=remind_days
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return RedirectResponse(url=f"/opportunities/{opportunity_id}", status_code=303)


@router.post("/opportunities/{opportunity_id}/score")
def score_opportunity(request: Request, opportunity_id: int) -> RedirectResponse:
    service = _service(request)
    if service.get_opportunity(opportunity_id) is None:
        raise HTTPException(status_code=404, detail="opportunity not found")

    try:
        _scoring_service(request).score_opportunity(opportunity_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return RedirectResponse(url=f"/opportunities/{opportunity_id}", status_code=303)


@router.post("/opportunities/{opportunity_id}/documents/tailored-resume")
def generate_tailored_resume(request: Request, opportunity_id: int) -> RedirectResponse:
    service = _service(request)
    if service.get_opportunity(opportunity_id) is None:
        raise HTTPException(status_code=404, detail="opportunity not found")

    try:
        _document_service(request).generate_tailored_resume(opportunity_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return RedirectResponse(url=f"/opportunities/{opportunity_id}", status_code=303)


@router.post("/opportunities/{opportunity_id}/documents/cover-letter")
def generate_cover_letter(request: Request, opportunity_id: int) -> RedirectResponse:
    service = _service(request)
    if service.get_opportunity(opportunity_id) is None:
        raise HTTPException(status_code=404, detail="opportunity not found")

    try:
        _document_service(request).generate_cover_letter(opportunity_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return RedirectResponse(url=f"/opportunities/{opportunity_id}", status_code=303)


@router.post("/opportunities/{opportunity_id}/documents/fit-report")
def generate_fit_report(request: Request, opportunity_id: int) -> RedirectResponse:
    service = _service(request)
    if service.get_opportunity(opportunity_id) is None:
        raise HTTPException(status_code=404, detail="opportunity not found")

    try:
        _document_service(request).generate_fit_report(opportunity_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return RedirectResponse(url=f"/opportunities/{opportunity_id}", status_code=303)


def _find_document(opportunity: dict, document_id: int) -> dict[str, Any] | None:
    for documents in opportunity["generated_documents"].values():
        for document in documents:
            if document["id"] == document_id:
                return document
    return None


@router.post("/opportunities/{opportunity_id}/documents/{document_id}/decision")
async def decide_generated_document(
    request: Request, opportunity_id: int, document_id: int
) -> RedirectResponse:
    service = _service(request)
    opportunity = service.get_opportunity(opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    if _find_document(opportunity, document_id) is None:
        raise HTTPException(status_code=404, detail="document not found")

    form = await request.form()
    try:
        decision = cast(
            Literal["approve", "reject"],
            _choice(str(form.get("decision", "")), {"approve", "reject"}),
        )
        rationale = str(form.get("rationale", "")).strip() or None
        _document_service(request).record_approval_decision(document_id, decision, rationale)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return RedirectResponse(url=f"/opportunities/{opportunity_id}", status_code=303)


def _export_filename(opportunity: dict, document: dict, extension: str) -> str:
    organization = opportunity.get("organization_name") or "opportunity"
    stem = f"{organization}-{document['document_type']}-v{document['version']}"
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-") or "document"
    return f"{safe_stem}.{extension}"


def _render_export(request: Request, opportunity: dict, document: dict, fmt: str) -> bytes:
    title = f"{document['document_type'].replace('_', ' ').title()} — {opportunity['title']}"

    if document["document_type"] == "tailored_resume":
        structured = parse_resume_content(document["content"])
        if structured is not None:
            profile = load_profile(request.app.state.settings.profile_path)
            return (
                render_resume_docx(profile, structured)
                if fmt == "docx"
                else render_resume_pdf(profile, structured)
            )
    elif document["document_type"] == "cover_letter":
        letter = parse_cover_letter_content(document["content"])
        if letter is not None:
            profile = load_profile(request.app.state.settings.profile_path)
            return (
                render_cover_letter_docx(profile, opportunity, letter)
                if fmt == "docx"
                else render_cover_letter_pdf(profile, opportunity, letter)
            )

    blocks = parse_markdown_subset(document["content"] or "")
    return render_docx(title, blocks) if fmt == "docx" else render_pdf(title, blocks)


@router.get("/opportunities/{opportunity_id}/documents/{document_id}/export.docx")
def export_document_docx(request: Request, opportunity_id: int, document_id: int) -> Response:
    service = _service(request)
    opportunity = service.get_opportunity(opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    document = _find_document(opportunity, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")

    content = _render_export(request, opportunity, document, "docx")
    filename = _export_filename(opportunity, document, "docx")
    return Response(
        content=content,
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/opportunities/{opportunity_id}/documents/{document_id}/export.pdf")
def export_document_pdf(request: Request, opportunity_id: int, document_id: int) -> Response:
    service = _service(request)
    opportunity = service.get_opportunity(opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    document = _find_document(opportunity, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")

    content = _render_export(request, opportunity, document, "pdf")
    filename = _export_filename(opportunity, document, "pdf")
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _choice(value: str, allowed: set[str]) -> str:
    if value not in allowed:
        raise ValueError(f"unsupported choice: {value}")
    return value


def _optional_float(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    return float(text)


def _optional_bool(value: object) -> bool | None:
    text = str(value or "unknown").lower()
    if text == "yes":
        return True
    if text == "no":
        return False
    if text == "unknown":
        return None
    raise ValueError(f"unsupported yes/no/unknown value: {text}")

