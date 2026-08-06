"""Remotive: general remote-jobs RSS feed, filtered to IT-relevant categories.

Unlike We Work Remotely's dedicated DevOps/Sysadmin category, Remotive's
feed spans every industry (verified live: Sales, Design, Writing, ...).
Each item does carry a structured `<category>` tag, though, so `fetch()`
filters to the two categories that match the constitution's focus areas
before any item becomes a `RawOpportunityRecord` — precise, structured
filtering, not a keyword guess. `Software Development` is deliberately
excluded: too broad, mostly generic app-dev roles outside scope, same
precision-over-recall bias as `OE-ADR-021`. See `OE-ADR-022`.

The feed's `?category=` query parameter is silently ignored (verified
live), so this filter runs client-side over the already-fetched items.
"""

import xml.etree.ElementTree as ET
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

DEFAULT_FEED_URL = "https://remotive.com/remote-jobs/feed"
_USER_AGENT = "OpportunityEngine/0.1 (personal opportunity-research tool)"
_RELEVANT_CATEGORIES = {"devops", "information technology"}

_JOB_TYPE_MAP: dict[str, EngagementType] = {
    "full_time": "full_time",
    "part_time": "part_time",
    "contract": "contract",
    "freelance": "contract",
    "temporary": "temporary",
}


def _default_http_get(url: str) -> str:
    response = httpx.get(url, headers={"User-Agent": _USER_AGENT}, timeout=10.0)
    response.raise_for_status()
    return response.text


class RemotiveAdapter:
    """Fetch and normalize IT-relevant Remotive listings."""

    source_name = "Remotive"
    source_type = "rss"

    def __init__(
        self,
        feed_url: str = DEFAULT_FEED_URL,
        http_get: Callable[[str], str] | None = None,
    ) -> None:
        self.base_url = feed_url
        self._http_get = http_get or _default_http_get

    def fetch(self) -> list[RawOpportunityRecord]:
        xml_text = self._http_get(self.base_url)
        root = ET.fromstring(xml_text)
        channel = root.find("channel")
        items = channel.findall("item") if channel is not None else []

        records = []
        retrieved_at = now_iso()
        for item in items:
            category = (item.findtext("category") or "").strip().lower()
            if category not in _RELEVANT_CATEGORIES:
                continue
            fields = {child.tag: (child.text or "") for child in item}
            link = fields.get("link", "").strip()
            guid = fields.get("guid", "").strip() or link
            if not guid:
                continue
            records.append(
                RawOpportunityRecord(
                    external_id=guid,
                    canonical_url=link or guid,
                    retrieved_at=retrieved_at,
                    raw_payload=fields,
                )
            )
        return records

    def normalize(self, record: RawOpportunityRecord) -> OpportunityInput:
        fields = record.raw_payload

        engagement_type = _JOB_TYPE_MAP.get(
            fields.get("type", "").strip().lower(), "unknown"
        )
        description = strip_html(fields.get("description", ""))

        # Structured data, not free text: an explicit "full_time" listing
        # is a permanent-employment role that would replace Scott's day
        # job, same reasoning as WeWorkRemotelyAdapter (OE-ADR-021).
        if engagement_type == "full_time":
            replaces_full_time_work = True
        elif engagement_type == "unknown":
            replaces_full_time_work = None
        else:
            replaces_full_time_work = False

        return OpportunityInput(
            title=fields.get("title", "").strip(),
            organization_name=fields.get("company", "").strip(),
            description=description,
            source_url=record.canonical_url,
            location_text=fields.get("location", "").strip(),
            remote_status="remote",
            engagement_type=engagement_type,
            tax_type="unknown",
            schedule_text="",
            compensation_min=None,
            compensation_max=None,
            compensation_period=None,
            requires_travel=extract_travel_signal(description),
            requires_relocation=extract_relocation_signal(description),
            requires_clearance=extract_clearance_signal(description),
            replaces_full_time_work=replaces_full_time_work,
        )
