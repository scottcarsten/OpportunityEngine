"""We Work Remotely: DevOps and Sysadmin RSS adapter.

The feed is publicly syndicated for exactly this purpose and needs no API
key. It publishes no compensation, tax-type, schedule, or travel/relocation/
clearance/full-time-replacement data, so `normalize()` maps those to
`"unknown"`/`None` — the existing hard-filter logic already routes unknown
values to `manual_review` rather than auto-approving them.
"""

import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from typing import Callable

import httpx

from backend.adapters.base import RawOpportunityRecord
from backend.models import EngagementType, OpportunityInput
from backend.timeutil import now_iso

DEFAULT_FEED_URL = "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss"
_USER_AGENT = "OpportunityEngine/0.1 (personal opportunity-research tool)"

_ENGAGEMENT_TYPE_MAP: dict[str, EngagementType] = {
    "full-time": "full_time",
    "contract": "contract",
    "part-time": "part_time",
    "temporary": "temporary",
}


class _HTMLTextExtractor(HTMLParser):
    """Collect the text content of an HTML fragment, discarding markup."""

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        self._chunks.append(data)

    def text(self) -> str:
        return " ".join(self._chunks)


def _strip_html(raw_html: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(raw_html)
    return parser.text()


def _default_http_get(url: str) -> str:
    response = httpx.get(url, headers={"User-Agent": _USER_AGENT}, timeout=10.0)
    response.raise_for_status()
    return response.text


class WeWorkRemotelyAdapter:
    """Fetch and normalize the We Work Remotely DevOps/Sysadmin RSS feed."""

    source_name = "We Work Remotely: DevOps and Sysadmin"
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
        title_field = fields.get("title", "").strip()
        if ": " in title_field:
            organization_name, title = title_field.split(": ", 1)
        else:
            organization_name, title = "", title_field

        location_parts = [
            fields.get("region", "").strip(),
            fields.get("country", "").strip(),
            fields.get("state", "").strip(),
        ]
        location_text = ", ".join(part for part in location_parts if part)

        engagement_type = _ENGAGEMENT_TYPE_MAP.get(
            fields.get("type", "").strip().lower(), "unknown"
        )

        description = _strip_html(fields.get("description", ""))

        return OpportunityInput(
            title=title,
            organization_name=organization_name,
            description=description,
            source_url=record.canonical_url,
            location_text=location_text,
            remote_status="remote",
            engagement_type=engagement_type,
            tax_type="unknown",
            schedule_text="",
            compensation_min=None,
            compensation_max=None,
            compensation_period=None,
            requires_travel=None,
            requires_relocation=None,
            requires_clearance=None,
            replaces_full_time_work=None,
        )
