"""Constitution validation tests."""

import json
from pathlib import Path

import pytest

from backend.services.constitution_service import load_constitution


def test_repository_constitution_is_valid() -> None:
    constitution = load_constitution(Path("config/constitution.json"))
    assert constitution.owner == "Scott Carsten"
    assert constitution.raw["principles"]["never_auto_apply"] is True


def test_missing_approval_gate_fails_closed(tmp_path: Path) -> None:
    source = json.loads(Path("config/constitution.json").read_text(encoding="utf-8"))
    source["human_approval_required"].remove("applications")
    path = tmp_path / "constitution.json"
    path.write_text(json.dumps(source), encoding="utf-8")

    with pytest.raises(RuntimeError, match="approval gates"):
        load_constitution(path)

