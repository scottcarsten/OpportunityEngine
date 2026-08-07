"""Tests for employer-reply monitoring via Microsoft Graph (OE-ADR-037)."""

from pathlib import Path

import httpx
import msal
import pytest

from backend.config import Settings
from backend.database import Database
from backend.graph_mail import (
    GraphAuthExpiredError,
    check_mail,
    correlate_opportunity,
    fetch_new_messages,
    format_mail_alert,
    get_access_token,
)
from backend.models import OpportunityInput
from backend.services.constitution_service import load_constitution
from backend.services.opportunity_service import OpportunityService


def _message(**overrides: object) -> dict:
    values: dict[str, object] = {
        "subject": "Re: Your application",
        "bodyPreview": "Thanks for applying, we'd like to schedule a call.",
        "from": {"emailAddress": {"name": "Jane Recruiter", "address": "jane@acmecorp.com"}},
    }
    values.update(overrides)
    return values


def _opportunity(**overrides: object) -> dict:
    values: dict[str, object] = {"id": 1, "title": "Cloud Administrator", "organization_name": "Acme Corp"}
    values.update(overrides)
    return values


def test_correlate_opportunity_matches_by_domain() -> None:
    message = _message()
    opportunities = [_opportunity()]

    matched_id = correlate_opportunity(message, opportunities)

    assert matched_id == 1


def test_correlate_opportunity_matches_by_sender_name() -> None:
    message = _message(
        **{"from": {"emailAddress": {"name": "Acme Corp Recruiting", "address": "noreply@greenhouse.io"}}}
    )
    opportunities = [_opportunity()]

    matched_id = correlate_opportunity(message, opportunities)

    assert matched_id == 1


def test_correlate_opportunity_returns_none_on_no_match() -> None:
    message = _message(
        **{"from": {"emailAddress": {"name": "Unrelated Sender", "address": "hello@totallydifferent.io"}}}
    )
    opportunities = [_opportunity()]

    matched_id = correlate_opportunity(message, opportunities)

    assert matched_id is None


def test_correlate_opportunity_handles_empty_list() -> None:
    assert correlate_opportunity(_message(), []) is None


def test_format_mail_alert_with_match() -> None:
    alert = format_mail_alert(_message(), _opportunity())

    assert "Jane Recruiter" in alert
    assert "Re: Your application" in alert
    assert "Cloud Administrator" in alert
    assert "Acme Corp" in alert
    assert "Thanks for applying" in alert


def test_format_mail_alert_without_match() -> None:
    alert = format_mail_alert(_message(), None)

    assert "unmatched" in alert


def test_fetch_new_messages_first_run_establishes_baseline_without_alerting(
    tmp_path: Path,
) -> None:
    delta_link_path = tmp_path / "delta_link.txt"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "value": [_message()],
                "@odata.deltaLink": "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta?token=abc",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    messages = fetch_new_messages("fake-token", delta_link_path, client=client)

    assert messages == []
    assert delta_link_path.exists()
    assert delta_link_path.read_text() == (
        "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta?token=abc"
    )


def test_fetch_new_messages_later_run_returns_new_messages(tmp_path: Path) -> None:
    delta_link_path = tmp_path / "delta_link.txt"
    delta_link_path.write_text("https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta?token=old")

    def handler(request: httpx.Request) -> httpx.Response:
        assert "token=old" in str(request.url)
        return httpx.Response(
            200,
            json={
                "value": [_message(subject="A new reply")],
                "@odata.deltaLink": "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta?token=new",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    messages = fetch_new_messages("fake-token", delta_link_path, client=client)

    assert len(messages) == 1
    assert messages[0]["subject"] == "A new reply"
    assert "token=new" in delta_link_path.read_text()


def test_fetch_new_messages_follows_pagination(tmp_path: Path) -> None:
    delta_link_path = tmp_path / "delta_link.txt"
    delta_link_path.write_text("https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta?token=old")
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if len(calls) == 1:
            return httpx.Response(
                200,
                json={
                    "value": [_message(subject="Page one")],
                    "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta?page=2",
                },
            )
        return httpx.Response(
            200,
            json={
                "value": [_message(subject="Page two")],
                "@odata.deltaLink": "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta?token=new",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    messages = fetch_new_messages("fake-token", delta_link_path, client=client)

    assert len(calls) == 2
    assert [m["subject"] for m in messages] == ["Page one", "Page two"]


def _opportunity_input(**overrides: object) -> OpportunityInput:
    values: dict[str, object] = {
        "title": "Cloud Administrator",
        "organization_name": "Acme Corp",
        "description": "Manage Azure and AWS environments for our engineering team.",
        "source_url": "https://example.com/jobs/1",
        "location_text": "United States",
        "remote_status": "remote",
        "engagement_type": "contract",
        "tax_type": "1099",
        "schedule_text": "After hours",
        "compensation_min": None,
        "compensation_max": None,
        "compensation_period": None,
        "requires_travel": False,
        "requires_relocation": False,
        "requires_clearance": False,
        "replaces_full_time_work": False,
    }
    values.update(overrides)
    return OpportunityInput(**values)


def test_check_mail_returns_empty_list_when_not_configured(tmp_path: Path) -> None:
    database = Database(database_path=tmp_path / "opportunity_engine.db")
    database.initialize()
    constitution = load_constitution(Path("config/constitution.json"))
    settings = Settings(ms_graph_client_id=None)

    alerts = check_mail(database, constitution, settings)

    assert alerts == []


def test_check_mail_end_to_end_correlates_and_formats_alerts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = Database(database_path=tmp_path / "opportunity_engine.db")
    database.initialize()
    constitution = load_constitution(Path("config/constitution.json"))
    service = OpportunityService(database, constitution)
    opportunity_id, _ = service.create_manual(_opportunity_input())
    service.mark_applied(opportunity_id)

    settings = Settings(
        ms_graph_client_id="fake-client-id",
        graph_delta_link_path=tmp_path / "delta_link.txt",
    )

    monkeypatch.setattr("backend.graph_mail.get_access_token", lambda s, **kwargs: "fake-token")
    monkeypatch.setattr(
        "backend.graph_mail.fetch_new_messages",
        lambda token, path, **kwargs: [_message()],
    )

    alerts = check_mail(database, constitution, settings)

    assert len(alerts) == 1
    assert alerts[0]["opportunity_id"] == opportunity_id
    assert "Cloud Administrator" in alerts[0]["text"]
    assert alerts[0]["subject"] == "Re: Your application"


def test_check_mail_raises_graph_auth_expired_when_auth_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = Database(database_path=tmp_path / "opportunity_engine.db")
    database.initialize()
    constitution = load_constitution(Path("config/constitution.json"))
    settings = Settings(ms_graph_client_id="fake-client-id")

    monkeypatch.setattr("backend.graph_mail.get_access_token", lambda s, **kwargs: None)

    with pytest.raises(GraphAuthExpiredError):
        check_mail(database, constitution, settings)


def test_check_mail_propagates_http_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = Database(database_path=tmp_path / "opportunity_engine.db")
    database.initialize()
    constitution = load_constitution(Path("config/constitution.json"))
    settings = Settings(ms_graph_client_id="fake-client-id")

    monkeypatch.setattr("backend.graph_mail.get_access_token", lambda s, **kwargs: "fake-token")

    def _raise(*args: object, **kwargs: object) -> None:
        raise httpx.ConnectError("boom")

    monkeypatch.setattr("backend.graph_mail.fetch_new_messages", _raise)

    with pytest.raises(httpx.HTTPError):
        check_mail(database, constitution, settings)


class _FakeMsalApp:
    """Stands in for msal.PublicClientApplication so get_access_token's
    interactive-vs-not branching can be tested without real network/auth."""

    def __init__(self, silent_result: dict | None) -> None:
        self._silent_result = silent_result
        self.device_flow_called = False

    def get_accounts(self) -> list[dict]:
        return [{"username": "test@example.com"}]

    def acquire_token_silent(self, scopes: list[str], account: dict) -> dict | None:
        return self._silent_result

    def initiate_device_flow(self, scopes: list[str]) -> dict:
        self.device_flow_called = True
        return {"user_code": "ABC123", "message": "go to https://microsoft.com/link"}

    def acquire_token_by_device_flow(self, flow: dict) -> dict:
        return {"access_token": "interactive-token"}


def test_get_access_token_non_interactive_skips_device_flow_on_silent_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_app = _FakeMsalApp(silent_result=None)
    monkeypatch.setattr(
        "backend.graph_mail._build_app",
        lambda settings: (fake_app, msal.SerializableTokenCache()),
    )
    settings = Settings(
        ms_graph_client_id="fake-client-id",
        graph_token_cache_path=tmp_path / "cache.json",
    )

    token = get_access_token(settings, interactive=False)

    assert token is None
    assert fake_app.device_flow_called is False


def test_get_access_token_interactive_falls_back_to_device_flow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_app = _FakeMsalApp(silent_result=None)
    monkeypatch.setattr(
        "backend.graph_mail._build_app",
        lambda settings: (fake_app, msal.SerializableTokenCache()),
    )
    settings = Settings(
        ms_graph_client_id="fake-client-id",
        graph_token_cache_path=tmp_path / "cache.json",
    )

    token = get_access_token(settings, interactive=True)

    assert token == "interactive-token"
    assert fake_app.device_flow_called is True
