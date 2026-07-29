"""Load and validate the authoritative project constitution."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REQUIRED_PRINCIPLES = {
    "master_resume_read_only",
    "generate_new_resume_per_application",
    "never_auto_apply",
    "never_send_email",
    "never_impersonate_scott",
    "never_make_external_commitments",
}

REQUIRED_APPROVALS = {
    "applications",
    "emails",
    "external_messages",
    "contracts",
    "identity_verification",
    "financial_commitments",
}


@dataclass(frozen=True)
class Constitution:
    """Validated immutable view of the constitution."""

    version: str
    owner: str
    raw: dict[str, Any]


def load_constitution(path: Path) -> Constitution:
    """Load the constitution or fail closed when it is incomplete."""
    if not path.is_file():
        raise RuntimeError(f"constitution not found: {path}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"constitution could not be loaded: {path}") from exc

    project = _require_mapping(data, "project")
    authority = _require_mapping(data, "authority")
    principles = _require_mapping(data, "principles")
    approvals = data.get("human_approval_required")

    if authority.get("authoritative") is not True:
        raise RuntimeError("constitution must declare itself authoritative")
    if authority.get("human_remains_in_control") is not True:
        raise RuntimeError("constitution must preserve human control")

    missing_principles = {
        key for key in REQUIRED_PRINCIPLES if principles.get(key) is not True
    }
    if missing_principles:
        missing = ", ".join(sorted(missing_principles))
        raise RuntimeError(f"constitution is missing required principles: {missing}")

    if not isinstance(approvals, list):
        raise RuntimeError("constitution approval requirements must be a list")
    missing_approvals = REQUIRED_APPROVALS.difference(approvals)
    if missing_approvals:
        missing = ", ".join(sorted(missing_approvals))
        raise RuntimeError(f"constitution is missing approval gates: {missing}")

    version = project.get("constitution_version")
    owner = authority.get("owner")
    if not isinstance(version, str) or not version:
        raise RuntimeError("constitution_version is required")
    if not isinstance(owner, str) or not owner:
        raise RuntimeError("constitution owner is required")

    return Constitution(version=version, owner=owner, raw=data)


def _require_mapping(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise RuntimeError(f"constitution section is missing or invalid: {key}")
    return value

