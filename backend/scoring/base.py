"""Scoring-provider contract.

Per `docs/ARCHITECTURE.md` §9, AI integration sits behind a provider
interface so domain code never depends on a specific model name. A provider
judges each dimension; the fixed weights below are deterministic app
arithmetic (`OE-ADR-006`), not something any provider controls — re-scoring
with the same weights stays comparable over time, and changing a weight is
a deliberate code change, not a per-run AI choice.
"""

from dataclasses import dataclass
from typing import Protocol

from backend.services.constitution_service import Constitution

# Collapses ARCHITECTURE §5.5's "skill alignment" and "M365/AWS/infra/
# sysadmin/cybersecurity relevance" into one component — both are the same
# signal against the constitution's focus_areas. "Source and extraction
# confidence" is ScoringResult.confidence directly, not a weighted component.
COMPONENT_WEIGHTS: dict[str, float] = {
    "skills_alignment": 0.35,
    "engagement_fit": 0.25,
    "compensation_potential": 0.20,
    "schedule_compatibility": 0.10,
    "requirement_risk": 0.10,
}


@dataclass(frozen=True)
class ComponentScore:
    code: str
    score: float
    explanation: str


@dataclass(frozen=True)
class ScoringResult:
    components: list[ComponentScore]
    confidence: float
    fit_summary: str
    concerns: str
    structured_payload: dict


class ScoringProvider(Protocol):
    """One AI (or other) provider capable of scoring an opportunity's fit."""

    provider_name: str
    model_name: str
    scoring_version: str
    prompt_version: str

    def score(self, opportunity: dict, constitution: Constitution) -> ScoringResult:
        """Judge each dimension in `COMPONENT_WEIGHTS` for one opportunity."""
        ...
