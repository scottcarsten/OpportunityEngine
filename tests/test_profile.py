"""Tests for static résumé profile loading."""

import json
from pathlib import Path

from backend.profile import load_profile


def test_load_profile_reads_expected_fields(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "full_name": "Jane Doe",
                "title_line": "Engineer | Consultant",
                "location": "Austin, TX",
                "phone": "555-000-1111",
                "email": "jane@example.com",
                "education": [{"institution": "State U", "degree": "B.S. CS"}],
                "certifications": ["CompTIA Security+"],
            }
        )
    )

    profile = load_profile(profile_path)

    assert profile["full_name"] == "Jane Doe"
    assert profile["education"][0]["institution"] == "State U"
    assert profile["certifications"] == ["CompTIA Security+"]
