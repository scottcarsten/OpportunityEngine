"""Manual opportunity vertical-slice tests."""

from pathlib import Path
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import Settings


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = Settings(
        database_path=tmp_path / "opportunity_engine.db",
        constitution_path=Path("config/constitution.json"),
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _form(**overrides: str) -> dict[str, str]:
    values = {
        "title": "Microsoft 365 Cloud Administrator",
        "organization_name": "Example Client",
        "description": "Manage Microsoft 365 and secure the tenant.",
        "source_url": "https://example.com/opportunity/123",
        "location_text": "United States",
        "remote_status": "remote",
        "engagement_type": "contract",
        "tax_type": "1099",
        "schedule_text": "After hours",
        "compensation_min": "85",
        "compensation_max": "125",
        "compensation_period": "hour",
        "requires_travel": "no",
        "requires_relocation": "no",
        "requires_clearance": "no",
        "replaces_full_time_work": "no",
    }
    values.update(overrides)
    return values


def test_manual_entry_becomes_eligible_and_is_displayed(client: TestClient) -> None:
    response = client.post("/opportunities", data=_form(), follow_redirects=False)
    assert response.status_code == 303

    detail = client.get(response.headers["location"])
    assert detail.status_code == 200
    assert "Microsoft 365 Cloud Administrator" in detail.text
    assert "Eligible" in detail.text
    assert detail.text.count(">Pass<") == 5

    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert "Example Client" in dashboard.text


def test_travel_requirement_is_ineligible(client: TestClient) -> None:
    response = client.post(
        "/opportunities",
        data=_form(title="Traveling Administrator", requires_travel="yes"),
        follow_redirects=False,
    )
    detail = client.get(response.headers["location"])
    assert "Ineligible" in detail.text
    assert "The opportunity must not require travel." in detail.text


def test_unknown_requirement_requires_manual_review(client: TestClient) -> None:
    response = client.post(
        "/opportunities",
        data=_form(title="Unclear Administrator", requires_clearance="unknown"),
        follow_redirects=False,
    )
    detail = client.get(response.headers["location"])
    assert "Manual review" in detail.text
    assert "The listing is unclear." in detail.text


def test_duplicate_entry_reuses_existing_record(client: TestClient) -> None:
    first = client.post("/opportunities", data=_form(), follow_redirects=False)
    second = client.post("/opportunities", data=_form(), follow_redirects=False)

    first_path = urlparse(first.headers["location"]).path
    second_path = urlparse(second.headers["location"]).path
    assert first_path == second_path
    assert "duplicate=1" in second.headers["location"]

    detail = client.get(second.headers["location"])
    assert "no duplicate was created" in detail.text

