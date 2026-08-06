"""Himalayas adapter tests: fetch/normalize against a fixture, no network."""

from pathlib import Path

from backend.adapters.himalayas import HimalayasAdapter

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "himalayas_sample.json"


def _adapter() -> HimalayasAdapter:
    fixture_text = FIXTURE_PATH.read_text(encoding="utf-8")
    return HimalayasAdapter(http_get=lambda url: fixture_text)


def test_fetch_returns_one_record_per_job_and_stops_at_total_count() -> None:
    records = _adapter().fetch()

    assert len(records) == 2
    first = records[0]
    assert first.external_id == (
        "https://himalayas.app/companies/acme-corp/jobs/senior-systems-administrator"
    )
    assert first.canonical_url == first.external_id


def test_normalize_maps_employment_type_and_compensation() -> None:
    adapter = _adapter()
    record = adapter.fetch()[0]

    supplied = adapter.normalize(record)

    assert supplied.title == "Senior Systems Administrator"
    assert supplied.organization_name == "Acme Corp"
    assert supplied.engagement_type == "contract"
    assert supplied.compensation_min == 90000
    assert supplied.compensation_max == 120000
    assert supplied.compensation_period == "year"
    assert supplied.location_text == "United States, Canada"
    assert supplied.remote_status == "remote"


def test_normalize_derives_full_time_replacement_from_employment_type() -> None:
    adapter = _adapter()
    records = adapter.fetch()

    contractor = adapter.normalize(records[0])
    full_time = adapter.normalize(records[1])

    assert contractor.replaces_full_time_work is False
    assert full_time.replaces_full_time_work is True


def test_normalize_extracts_signals_from_description() -> None:
    adapter = _adapter()
    records = adapter.fetch()

    contractor = adapter.normalize(records[0])
    full_time = adapter.normalize(records[1])

    assert contractor.requires_travel is False
    assert full_time.requires_travel is True
    assert full_time.requires_clearance is True


def test_normalize_strips_html_from_description() -> None:
    adapter = _adapter()
    record = adapter.fetch()[0]

    supplied = adapter.normalize(record)

    assert "<" not in supplied.description
    assert "Azure and AWS" in supplied.description
