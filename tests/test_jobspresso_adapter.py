"""Jobspresso adapter tests: fetch/normalize against a fixture, no network."""

from pathlib import Path

from backend.adapters.jobspresso import JobspressoAdapter

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "jobspresso_sample.rss"


def _adapter() -> JobspressoAdapter:
    fixture_text = FIXTURE_PATH.read_text(encoding="utf-8")
    return JobspressoAdapter(http_get=lambda url: fixture_text)


def test_fetch_filters_out_irrelevant_listings() -> None:
    records = _adapter().fetch()

    assert len(records) == 1
    assert records[0].raw_payload["title"] == "Remote Cloud Infrastructure Engineer"


def test_normalize_splits_company_and_location_from_dc_creator() -> None:
    adapter = _adapter()
    record = adapter.fetch()[0]

    supplied = adapter.normalize(record)

    assert supplied.organization_name == "Acme Corp"
    assert supplied.location_text == "US, Canada, Europe"
    assert supplied.remote_status == "remote"
    assert supplied.engagement_type == "unknown"
    assert supplied.replaces_full_time_work is None


def test_normalize_extracts_signals_from_description() -> None:
    adapter = _adapter()
    record = adapter.fetch()[0]

    supplied = adapter.normalize(record)

    assert supplied.requires_relocation is False
    assert "<" not in supplied.description
