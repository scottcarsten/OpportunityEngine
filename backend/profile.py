"""Static identity/reference data for résumé rendering.

Deliberately separate from `resume_sources`: this is Scott's fixed
identity data (name, contact, education, certifications) — the AI never
sees or touches it. Only used at render time by
`backend/documents/resume_render.py`. See `OE-ADR-026`.
"""

import json
from pathlib import Path


def load_profile(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
