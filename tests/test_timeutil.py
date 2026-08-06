"""Tests for shared timestamp-parsing helpers."""

from backend.timeutil import from_unix_timestamp, parse_rfc822


def test_parse_rfc822_parses_a_real_wwr_style_date() -> None:
    assert parse_rfc822("Wed, 02 Sep 2026 07:30:43 +0000") == "2026-09-02T07:30:43.000000Z"


def test_parse_rfc822_handles_missing_or_invalid_input() -> None:
    assert parse_rfc822(None) is None
    assert parse_rfc822("") is None
    assert parse_rfc822("not a date") is None


def test_from_unix_timestamp_parses_a_real_himalayas_style_value() -> None:
    assert from_unix_timestamp(1787297084) == "2026-08-21T07:24:44.000000Z"


def test_from_unix_timestamp_handles_missing_or_invalid_input() -> None:
    assert from_unix_timestamp(None) is None
    assert from_unix_timestamp("not a number") is None
