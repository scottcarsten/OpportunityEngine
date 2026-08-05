"""Source-adapter contract.

Per `docs/ARCHITECTURE.md` §5, collection is two stages: adapters fetch and
preserve raw evidence without interpreting it, and normalization maps that
evidence into the canonical `OpportunityInput` shape. Adapters must not
score, apply, message, or generate application documents.
"""

from dataclasses import dataclass
from typing import Any, Protocol

from backend.models import OpportunityInput


@dataclass(frozen=True)
class RawOpportunityRecord:
    """Raw evidence for one listing, before any normalization."""

    external_id: str
    canonical_url: str
    retrieved_at: str
    raw_payload: dict[str, Any]


class SourceAdapter(Protocol):
    """One approved opportunity source."""

    source_name: str
    source_type: str
    base_url: str | None

    def fetch(self) -> list[RawOpportunityRecord]:
        """Fetch current listings, preserving source evidence."""
        ...

    def normalize(self, record: RawOpportunityRecord) -> OpportunityInput:
        """Map one raw record into the canonical opportunity model."""
        ...
