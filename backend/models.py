"""Domain models for opportunity entry and review."""

from dataclasses import dataclass
from typing import Literal


RemoteStatus = Literal["remote", "hybrid", "onsite", "unknown"]
EngagementType = Literal[
    "contract",
    "consulting",
    "project",
    "part_time",
    "full_time",
    "temporary",
    "unknown",
]
TaxType = Literal["1099", "w2", "corp_to_corp", "unknown"]


@dataclass(frozen=True)
class OpportunityInput:
    """User-supplied opportunity data before normalization."""

    title: str
    organization_name: str
    description: str
    source_url: str
    location_text: str
    remote_status: RemoteStatus
    engagement_type: EngagementType
    tax_type: TaxType
    schedule_text: str
    compensation_min: float | None
    compensation_max: float | None
    compensation_period: str | None
    requires_travel: bool | None
    requires_relocation: bool | None
    requires_clearance: bool | None
    replaces_full_time_work: bool | None
    expires_at: str | None = None

