"""Himalayas: free, unauthenticated JSON search API adapter.

Unlike We Work Remotely's dedicated DevOps/Sysadmin RSS category,
Himalayas' feeds are "every remote job, every industry." Its search API
(`/jobs/api/search`) supports a boolean-`OR` free-text query, so `fetch()`
asks for exactly the roles in the constitution's focus areas up front —
the relevance filter is the query itself, not a post-hoc scan. Verified
live (2026-08-06): the combined query below returned 52 highly relevant
results (Systems Administrator, IT Infrastructure Engineer, Cloud
Engineer, Azure Engineer, ...). See `OE-ADR-022`.

This is also the first source with real structured compensation
(`minSalary`/`maxSalary`/`salaryPeriod`) and a clean `employmentType`
enum — no free-text guessing needed for either.
"""

import json
from typing import Callable

import httpx

from backend.adapters.base import RawOpportunityRecord
from backend.adapters.html_text import strip_html
from backend.adapters.signal_extraction import (
    extract_clearance_signal,
    extract_relocation_signal,
    extract_travel_signal,
)
from backend.models import EngagementType, OpportunityInput
from backend.timeutil import now_iso

SEARCH_URL = "https://himalayas.app/jobs/api/search"
_USER_AGENT = "OpportunityEngine/0.1 (personal opportunity-research tool)"
_QUERY = (
    "devops OR sysadmin OR system administrator OR cloud engineer OR "
    "cybersecurity OR it infrastructure OR network administrator OR "
    "office 365 OR azure"
)
_PAGE_LIMIT = 20
_MAX_RECORDS = 200

_EMPLOYMENT_TYPE_MAP: dict[str, EngagementType] = {
    "full time": "full_time",
    "part time": "part_time",
    "contractor": "contract",
    "temporary": "temporary",
}
_SALARY_PERIOD_MAP: dict[str, str] = {
    "annual": "year",
    "hourly": "hour",
    "daily": "day",
    "weekly": "week",
    "monthly": "month",
}


def _default_http_get(url: str) -> str:
    response = httpx.get(url, headers={"User-Agent": _USER_AGENT}, timeout=10.0)
    response.raise_for_status()
    return response.text


class HimalayasAdapter:
    """Fetch and normalize IT/infrastructure-relevant Himalayas listings."""

    source_name = "Himalayas"
    source_type = "json_api"
    base_url = SEARCH_URL

    def __init__(self, http_get: Callable[[str], str] | None = None) -> None:
        self._http_get = http_get or _default_http_get

    def fetch(self) -> list[RawOpportunityRecord]:
        records: list[RawOpportunityRecord] = []
        retrieved_at = now_iso()
        offset = 0
        while offset < _MAX_RECORDS:
            query = httpx.QueryParams({"q": _QUERY, "limit": _PAGE_LIMIT, "offset": offset})
            url = f"{SEARCH_URL}?{query}"
            payload = json.loads(self._http_get(url))
            jobs = payload.get("jobs", [])
            if not jobs:
                break
            for job in jobs:
                guid = (job.get("guid") or "").strip()
                if not guid:
                    continue
                records.append(
                    RawOpportunityRecord(
                        external_id=guid,
                        canonical_url=job.get("applicationLink") or guid,
                        retrieved_at=retrieved_at,
                        raw_payload=job,
                    )
                )
            offset += _PAGE_LIMIT
            if offset >= payload.get("totalCount", 0):
                break
        return records

    def normalize(self, record: RawOpportunityRecord) -> OpportunityInput:
        job = record.raw_payload

        engagement_type = _EMPLOYMENT_TYPE_MAP.get(
            (job.get("employmentType") or "").strip().lower(), "unknown"
        )

        location_text = ", ".join(job.get("locationRestrictions") or [])
        description = strip_html(job.get("description") or "")

        compensation_period = _SALARY_PERIOD_MAP.get(
            (job.get("salaryPeriod") or "").strip().lower(), "unknown"
        )

        # Structured data, not free text: an explicit "Full Time" listing
        # is a permanent-employment role that would replace Scott's day
        # job, same reasoning as WeWorkRemotelyAdapter (OE-ADR-021).
        if engagement_type == "full_time":
            replaces_full_time_work = True
        elif engagement_type == "unknown":
            replaces_full_time_work = None
        else:
            replaces_full_time_work = False

        return OpportunityInput(
            title=job.get("title") or "",
            organization_name=job.get("companyName") or "",
            description=description,
            source_url=record.canonical_url,
            location_text=location_text,
            remote_status="remote",
            engagement_type=engagement_type,
            tax_type="unknown",
            schedule_text="",
            compensation_min=job.get("minSalary"),
            compensation_max=job.get("maxSalary"),
            compensation_period=compensation_period,
            requires_travel=extract_travel_signal(description),
            requires_relocation=extract_relocation_signal(description),
            requires_clearance=extract_clearance_signal(description),
            replaces_full_time_work=replaces_full_time_work,
        )
