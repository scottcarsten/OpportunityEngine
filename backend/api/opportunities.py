"""Server-rendered manual opportunity workflow."""

from pathlib import Path
from typing import Literal, cast

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from backend.models import EngagementType, OpportunityInput, RemoteStatus, TaxType
from backend.services.opportunity_service import OpportunityService


router = APIRouter()
templates = Jinja2Templates(directory=str(Path("templates")))


def _service(request: Request) -> OpportunityService:
    return OpportunityService(
        database=request.app.state.database,
        constitution=request.app.state.constitution,
    )


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"opportunities": _service(request).list_opportunities()},
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
    opportunity = _service(request).get_opportunity(opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    return templates.TemplateResponse(
        request=request,
        name="opportunity_detail.html",
        context={"opportunity": opportunity, "duplicate": duplicate == 1},
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

