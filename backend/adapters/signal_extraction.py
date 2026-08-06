"""Deterministic hard-filter signal extraction from free-text descriptions.

Source-agnostic: any adapter whose listing text mentions travel,
relocation, or clearance requirements can reuse these. Per `OE-ADR-006`,
hard filters run deterministically before any AI judgment, so this stays
pattern-matching, never a model call.

Biased toward precision over recall: each function returns `None` (leaves
the field as "unknown", still routed to manual review by
`OpportunityService._evaluate_filters`) whenever a description doesn't
contain a clear, unambiguous phrase. Missing a signal just means Scott
reviews it, same as today; guessing wrong could let a bad-fit opportunity
auto-pass a hard filter — see `OE-ADR-021`.
"""

import re

_TRAVEL_REQUIRED = re.compile(
    r"\b(?:travel(?:ing)? (?:is )?required|requires? travel|"
    r"\d{1,3}%\s*travel|occasional travel|"
    r"(?:some|willing to) travel)\b",
    re.IGNORECASE,
)
_TRAVEL_NOT_REQUIRED = re.compile(
    r"\bno travel (?:is )?required|travel (?:is )?not required|0%\s*travel\b",
    re.IGNORECASE,
)

_RELOCATION_REQUIRED = re.compile(
    r"\b(?:relocation (?:is )?required|must relocate|willing to relocate)\b",
    re.IGNORECASE,
)
_RELOCATION_NOT_REQUIRED = re.compile(
    r"\bno relocation (?:is )?required|relocation (?:is )?not required\b",
    re.IGNORECASE,
)

_CLEARANCE_REQUIRED = re.compile(
    r"\b(?:security clearance (?:is )?required|"
    r"must (?:hold|have) (?:an? )?(?:active )?(?:security )?clearance|"
    r"ts/sci|top secret clearance|active clearance)\b",
    re.IGNORECASE,
)
_CLEARANCE_NOT_REQUIRED = re.compile(
    r"\bno (?:security )?clearance (?:is )?required|"
    r"clearance (?:is )?not required\b",
    re.IGNORECASE,
)


def _scan(description: str, required: re.Pattern, not_required: re.Pattern) -> bool | None:
    if not description:
        return None
    if not_required.search(description):
        return False
    if required.search(description):
        return True
    return None


def extract_travel_signal(description: str) -> bool | None:
    return _scan(description, _TRAVEL_REQUIRED, _TRAVEL_NOT_REQUIRED)


def extract_relocation_signal(description: str) -> bool | None:
    return _scan(description, _RELOCATION_REQUIRED, _RELOCATION_NOT_REQUIRED)


def extract_clearance_signal(description: str) -> bool | None:
    return _scan(description, _CLEARANCE_REQUIRED, _CLEARANCE_NOT_REQUIRED)
