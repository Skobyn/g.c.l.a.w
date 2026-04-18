"""gclaw.guardrails — inline input/output guardrails for agent turns.

Public API:
  - :class:`GuardrailService` — the orchestrator the runner calls.
  - :class:`GuardrailResult` / :class:`Violation` / :class:`Outcome` —
    the result surface emitted as span attributes.
  - :class:`GuardrailBlockedError` — raised by the runner when outcome
    is BLOCK.
  - :class:`GuardrailProfile` — declarative validator bundle.
"""

from gclaw.guardrails.models import (
    GuardrailBlockedError,
    GuardrailResult,
    Outcome,
    Violation,
)
from gclaw.guardrails.service import GuardrailProfile, GuardrailService

__all__ = [
    "GuardrailService",
    "GuardrailProfile",
    "GuardrailResult",
    "GuardrailBlockedError",
    "Outcome",
    "Violation",
]
