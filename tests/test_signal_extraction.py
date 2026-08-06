"""Deterministic hard-filter signal extraction tests."""

from backend.adapters.signal_extraction import (
    extract_clearance_signal,
    extract_relocation_signal,
    extract_travel_signal,
)


def test_travel_required_phrase_detected() -> None:
    assert extract_travel_signal("Some travel required for client visits.") is True


def test_travel_not_required_phrase_detected() -> None:
    assert extract_travel_signal("Fully remote. No travel required.") is False


def test_travel_signal_unknown_when_unmentioned() -> None:
    assert extract_travel_signal("Manage our cloud infrastructure day to day.") is None


def test_relocation_required_phrase_detected() -> None:
    assert extract_relocation_signal("Candidates must relocate to our hub city.") is True


def test_relocation_not_required_phrase_detected() -> None:
    assert extract_relocation_signal("Remote role; relocation is not required.") is False


def test_relocation_signal_unknown_when_unmentioned() -> None:
    assert extract_relocation_signal("Own our AWS and Azure environments.") is None


def test_clearance_required_phrase_detected() -> None:
    assert extract_clearance_signal("Must hold an active security clearance.") is True


def test_clearance_not_required_phrase_detected() -> None:
    assert extract_clearance_signal("No security clearance required for this role.") is False


def test_clearance_signal_unknown_when_unmentioned() -> None:
    assert extract_clearance_signal("Own identity and access management.") is None


def test_empty_description_is_unknown_for_all_signals() -> None:
    assert extract_travel_signal("") is None
    assert extract_relocation_signal("") is None
    assert extract_clearance_signal("") is None
