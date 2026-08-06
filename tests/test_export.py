"""Tests for DOCX/PDF rendering of parsed document blocks."""

from backend.documents.export import render_docx, render_pdf
from backend.documents.markdown_subset import parse

_SAMPLE_BLOCKS = parse(
    "# Fit Report: R&D Engineer\n\n**Overall score: 82/100**\n\n"
    "A plain paragraph with an ampersand (R&D) and a <tag>-looking bit."
)


def test_render_docx_produces_a_valid_zip_signature() -> None:
    content = render_docx("Test Title", _SAMPLE_BLOCKS)

    assert content[:4] == b"PK\x03\x04"
    assert len(content) > 0


def test_render_pdf_produces_a_valid_pdf_signature() -> None:
    content = render_pdf("Test Title", _SAMPLE_BLOCKS)

    assert content[:5] == b"%PDF-"
    assert len(content) > 0


def test_render_docx_handles_special_characters_without_raising() -> None:
    blocks = parse("Title with & ampersand and <angle> brackets.")

    render_docx("Title & More", blocks)


def test_render_pdf_handles_special_characters_without_raising() -> None:
    blocks = parse("Title with & ampersand and <angle> brackets.")

    render_pdf("Title & More", blocks)


def test_render_docx_round_trips_readable_text() -> None:
    import io

    import docx

    content = render_docx("Résumé Draft", _SAMPLE_BLOCKS)
    document = docx.Document(io.BytesIO(content))
    full_text = "\n".join(p.text for p in document.paragraphs)

    assert "Fit Report: R&D Engineer" in full_text
    assert "Overall score: 82/100" in full_text
