"""Tests for the narrow Markdown subset parser used by document export."""

from backend.documents.markdown_subset import parse


def test_plain_prose_with_no_markdown_becomes_a_single_paragraph() -> None:
    blocks = parse("Dear Hiring Team,\n\nI am writing to express interest.")

    assert blocks == [
        {"type": "paragraph", "runs": [{"text": "Dear Hiring Team,", "bold": False}]},
        {"type": "paragraph", "runs": [{"text": "I am writing to express interest.", "bold": False}]},
    ]


def test_headings_detected_at_each_level() -> None:
    blocks = parse("# Title\n\n## Section\n\n### Subsection")

    assert [b["level"] for b in blocks] == [1, 2, 3]
    assert all(b["type"] == "heading" for b in blocks)
    assert blocks[0]["runs"][0]["text"] == "Title"


def test_bold_span_detected_within_a_paragraph() -> None:
    blocks = parse("**Overall score: 82/100**")

    assert blocks[0]["runs"] == [{"text": "Overall score: 82/100", "bold": True}]


def test_mixed_bold_and_plain_runs_in_one_paragraph() -> None:
    blocks = parse("Confidence: **90%** based on the listing.")

    assert blocks[0]["runs"] == [
        {"text": "Confidence: ", "bold": False},
        {"text": "90%", "bold": True},
        {"text": " based on the listing.", "bold": False},
    ]


def test_heading_immediately_followed_by_text_without_blank_line() -> None:
    blocks = parse("## Details\nSome more text here.")

    assert blocks[0] == {"type": "heading", "level": 2, "runs": [{"text": "Details", "bold": False}]}
    assert blocks[1] == {
        "type": "paragraph",
        "runs": [{"text": "Some more text here.", "bold": False}],
    }


def test_blank_lines_split_content_into_separate_blocks() -> None:
    blocks = parse("First paragraph.\n\n\nSecond paragraph.")

    assert len(blocks) == 2
