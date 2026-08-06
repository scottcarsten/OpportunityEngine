"""Remotive adapter tests: fetch/normalize against a fixture, no network."""

from pathlib import Path

from backend.adapters.remotive import RemotiveAdapter

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "remotive_sample.rss"


def _adapter() -> RemotiveAdapter:
    fixture_text = FIXTURE_PATH.read_text(encoding="utf-8")
    return RemotiveAdapter(http_get=lambda url: fixture_text)


def test_fetch_filters_to_relevant_categories_only() -> None:
    records = _adapter().fetch()

    assert len(records) == 2
    titles = {r.raw_payload["title"] for r in records}
    assert titles == {"Senior DevOps Engineer", "IT Support Specialist"}
    assert "Sales Development Representative" not in titles


def test_normalize_maps_job_type_and_location() -> None:
    adapter = _adapter()
    record = adapter.fetch()[0]

    supplied = adapter.normalize(record)

    assert supplied.title == "Senior DevOps Engineer"
    assert supplied.organization_name == "Acme Corp"
    assert supplied.engagement_type == "contract"
    assert supplied.location_text == "Worldwide"
    assert supplied.remote_status == "remote"


def test_normalize_derives_full_time_replacement_from_job_type() -> None:
    adapter = _adapter()
    records = adapter.fetch()

    contract = adapter.normalize(records[0])
    full_time = adapter.normalize(records[1])

    assert contract.replaces_full_time_work is False
    assert full_time.replaces_full_time_work is True


def test_normalize_extracts_signals_from_description() -> None:
    adapter = _adapter()
    records = adapter.fetch()

    contract = adapter.normalize(records[0])
    full_time = adapter.normalize(records[1])

    assert contract.requires_travel is False
    assert full_time.requires_clearance is True
