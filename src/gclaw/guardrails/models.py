"""Data models for the guardrail result surface."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Outcome(str, Enum):
    """What the caller should do with the model output."""

    PASS = "pass"       # all validators ok
    WARN = "warn"       # at least one validator raised a soft violation
    BLOCK = "block"     # at least one validator raised a hard violation

    @classmethod
    def worst(cls, outcomes: list["Outcome"]) -> "Outcome":
        if not outcomes:
            return cls.PASS
        order = {cls.PASS: 0, cls.WARN: 1, cls.BLOCK: 2}
        return max(outcomes, key=lambda o: order[o])


@dataclass
class Violation:
    """A single guardrail finding. Cheap to serialize for span attrs."""

    validator: str
    outcome: Outcome
    message: str
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "validator": self.validator,
            "outcome": self.outcome.value,
            "message": self.message,
            "details": self.details,
        }


@dataclass
class GuardrailResult:
    outcome: Outcome
    violations: list[Violation] = field(default_factory=list)
    duration_ms: int = 0

    def violations_as_json(self) -> list[dict]:
        return [v.to_dict() for v in self.violations]


class GuardrailBlockedError(RuntimeError):
    """Raised by the runner when a guardrail outcome is BLOCK.

    Carries the ``GuardrailResult`` so callers (and the dashboard) can
    inspect which validator tripped.
    """

    def __init__(self, result: GuardrailResult) -> None:
        summary = ", ".join(
            f"{v.validator}:{v.outcome.value}" for v in result.violations
        ) or "blocked"
        super().__init__(f"guardrail blocked: {summary}")
        self.result = result
