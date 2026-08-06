"""Parse the narrow Markdown subset actually observed in generated documents.

Real generated content is inconsistent: some documents are plain prose,
some use `#`/`##`/`###` headers and `**bold**` (verified against real
Opus 5 output — see `OE-ADR-025`). This parser only recognizes those
three constructs. Anything else (lists, links, tables) falls through as
plain paragraph text rather than being mis-rendered — not observed in
real output, and an explicit scope boundary rather than an oversight.
"""

import re

_HEADING_PATTERN = re.compile(r"^(#{1,3})\s+(.*)$")
_BOLD_PATTERN = re.compile(r"\*\*(.+?)\*\*")


def _parse_runs(text: str) -> list[dict]:
    runs: list[dict] = []
    position = 0
    for match in _BOLD_PATTERN.finditer(text):
        if match.start() > position:
            runs.append({"text": text[position : match.start()], "bold": False})
        runs.append({"text": match.group(1), "bold": True})
        position = match.end()
    if position < len(text):
        runs.append({"text": text[position:], "bold": False})
    return runs or [{"text": "", "bold": False}]


def parse(content: str) -> list[dict]:
    """Split `content` into typed blocks: `{"type": "heading"|"paragraph", ...}`.

    A block is a heading only if its *first line* matches `#{1,3} text`;
    any remaining lines in that same block become a following paragraph,
    so a heading immediately followed by body text (no blank line) still
    splits correctly, not just the blank-line-separated convention the
    real generated content actually uses.
    """
    blocks: list[dict] = []
    for raw_block in re.split(r"\n\s*\n", content.strip()):
        raw_block = raw_block.strip()
        if not raw_block:
            continue
        lines = raw_block.splitlines()
        heading_match = _HEADING_PATTERN.match(lines[0])
        if heading_match:
            blocks.append(
                {
                    "type": "heading",
                    "level": len(heading_match.group(1)),
                    "runs": _parse_runs(heading_match.group(2).strip()),
                }
            )
            remaining = [line.strip() for line in lines[1:] if line.strip()]
            if remaining:
                blocks.append({"type": "paragraph", "runs": _parse_runs(" ".join(remaining))})
        else:
            text = " ".join(line.strip() for line in lines)
            blocks.append({"type": "paragraph", "runs": _parse_runs(text)})
    return blocks
