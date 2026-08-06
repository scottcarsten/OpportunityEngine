"""Jobspresso: general remote-jobs RSS feed, filtered by keyword relevance.

Unlike We Work Remotely's dedicated DevOps/Sysadmin category, Jobspresso's
feed spans every industry (verified live: a stock/options trader was the
first item) and exposes no structured category or engagement-type field
at all — its category-specific feed URLs return zero items live. The only
available filter is a deterministic, precision-biased keyword scan over
title and description, the same bias `OE-ADR-021` established for
hard-filter signal extraction, applied here to relevance instead. Missing
a borderline listing is fine; flooding the queue with irrelevant ones is
not. See `OE-ADR-022`.
"""

import html
import re
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
from backend.models import OpportunityInput
from backend.timeutil import now_iso

DEFAULT_FEED_URL = "https://jobspresso.co/feed/?post_type=job_listing"
_USER_AGENT = "OpportunityEngine/0.1 (personal opportunity-research tool)"
_DC_CREATOR_TAG = "{http://purl.org/dc/elements/1.1/}creator"
_CREATOR_SPLIT = re.compile(r"<br\s*/?>", re.IGNORECASE)
_LOCATION_MARKER = re.compile(r"^[^\w]*")

_RELEVANT_KEYWORDS = (
    "devops",
    "sysadmin",
    "system administrator",
    "cloud engineer",
    "cloud administrator",
    "cloud infrastructure",
    "cloud architect",
    "cloud security",
    "it infrastructure",
    "infrastructure engineer",
    "cybersecurity",
    "network administrator",
    "network admin",
    "office 365",
    "azure",
    "aws",
)


def _default_http_get(url: str) -> str:
    response = httpx.get(url, headers={"User-Agent": _USER_AGENT}, timeout=10.0)
    response.raise_for_status()
    return response.text


def _is_relevant(title: str, description: str) -> bool:
    haystack = f"{title} {description}".lower()
    return any(keyword in haystack for keyword in _RELEVANT_KEYWORDS)


class JobspressoAdapter:
    """Fetch and normalize IT-relevant Jobspresso listings."""

    source_name = "Jobspresso"
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
            title = (item.findtext("title") or "").strip()
            description = strip_html(item.findtext("description") or "")
            if not _is_relevant(title, description):
                continue
            link = (item.findtext("link") or "").strip()
            guid = (item.findtext("guid") or "").strip() or link
            if not guid:
                continue
            fields = {child.tag: (child.text or "") for child in item}
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
        title = fields.get("title", "").strip()
        description = strip_html(fields.get("description", ""))

        creator = fields.get(_DC_CREATOR_TAG, "")
        parts = _CREATOR_SPLIT.split(creator, maxsplit=1)
        organization_name = html.unescape(parts[0]).strip()
        location_text = ""
        if len(parts) > 1:
            location_text = _LOCATION_MARKER.sub("", html.unescape(parts[1])).strip()

        return OpportunityInput(
            title=title,
            organization_name=organization_name,
            description=description,
            source_url=record.canonical_url,
            location_text=location_text,
            remote_status="remote",
            engagement_type="unknown",
            tax_type="unknown",
            schedule_text="",
            compensation_min=None,
            compensation_max=None,
            compensation_period=None,
            requires_travel=extract_travel_signal(description),
            requires_relocation=extract_relocation_signal(description),
            requires_clearance=extract_clearance_signal(description),
            replaces_full_time_work=None,
        )
