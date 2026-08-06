"""Shared HTML-to-plain-text stripping for adapters whose feeds embed markup."""

from html.parser import HTMLParser


class _HTMLTextExtractor(HTMLParser):
    """Collect the text content of an HTML fragment, discarding markup."""

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        self._chunks.append(data)

    def text(self) -> str:
        return " ".join(self._chunks)


def strip_html(raw_html: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(raw_html)
    return parser.text()
