"""Document-generation-provider contract.

Mirrors `backend/scoring/base.py`: domain code depends on this Protocol,
never on a specific model, so the concrete provider stays swappable and
tests can supply a fake with zero real API calls.
"""

from dataclasses import dataclass
from typing import Protocol

from backend.services.constitution_service import Constitution


@dataclass(frozen=True)
class DocumentGenerationResult:
    content: str
    unsupported_claims: list[str]
    structured_payload: dict


class DocumentGenerationProvider(Protocol):
    """One AI (or other) provider capable of drafting a tailored résumé."""

    provider_name: str
    model_name: str
    prompt_version: str

    def generate_tailored_resume(
        self,
        opportunity: dict,
        master_resume: dict,
        resume_bytes: bytes,
        constitution: Constitution,
    ) -> DocumentGenerationResult:
        """Draft a tailored résumé for one opportunity, grounded in the master résumé.

        `master_resume` is a `ResumeService.get_current_master()` dict
        (has `mime_type`, `file_name`, `version`); `resume_bytes` is the
        raw file content read from its `storage_path`. The provider — not
        the caller — decides how to encode it for the model.
        """
        ...
