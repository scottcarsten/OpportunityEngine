"""We Work Remotely adapter tests: fetch/normalize against a fixture, no network."""

from pathlib import Path

from backend.adapters.we_work_remotely import WeWorkRemotelyAdapter

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "we_work_remotely_sample.rss"


def _adapter() -> WeWorkRemotelyAdapter:
    fixture_text = FIXTURE_PATH.read_text(encoding="utf-8")
    return WeWorkRemotelyAdapter(http_get=lambda url: fixture_text)


def test_fetch_returns_one_record_per_item_with_raw_evidence() -> None:
    records = _adapter().fetch()

    assert len(records) == 2
    first = records[0]
    assert first.external_id == "https://weworkremotely.com/remote-jobs/acme-corp-senior-cloud-administrator"
    assert first.canonical_url == first.external_id
    assert first.raw_payload["title"] == "Acme Corp: Senior Cloud Administrator"


def test_normalize_splits_company_from_title_and_maps_engagement_type() -> None:
    adapter = _adapter()
    record = adapter.fetch()[0]

    supplied = adapter.normalize(record)

    assert supplied.organization_name == "Acme Corp"
    assert supplied.title == "Senior Cloud Administrator"
    assert supplied.engagement_type == "contract"
    assert supplied.remote_status == "remote"
    assert supplied.source_url == record.canonical_url


def test_normalize_strips_html_from_description() -> None:
    adapter = _adapter()
    record = adapter.fetch()[0]

    supplied = adapter.normalize(record)

    assert "<" not in supplied.description
    assert "Manage Azure and AWS" in supplied.description


def test_normalize_falls_back_when_title_has_no_colon() -> None:
    adapter = _adapter()
    record = adapter.fetch()[1]

    supplied = adapter.normalize(record)

    assert supplied.organization_name == ""
    assert supplied.title == "Overseas Logistics Coordinator"


def test_normalize_marks_unavailable_fields_unknown() -> None:
    adapter = _adapter()
    record = adapter.fetch()[0]

    supplied = adapter.normalize(record)

    assert supplied.tax_type == "unknown"
    assert supplied.compensation_min is None
    assert supplied.requires_travel is None
    assert supplied.requires_relocation is None
    assert supplied.requires_clearance is None
    assert supplied.replaces_full_time_work is None
