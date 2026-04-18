"""Guardrail orchestration — fans out to every configured validator and
merges their findings into a single :class:`GuardrailResult`.

Authority-scoped profiles let the caller ship STRICT guardrails on
high-blast-radius tool chains (Workspace/Comms writes) while leaving
research chat LOOSE. Profiles map to the validator set and to each
validator's severity.

All validators run in parallel (``asyncio.gather``) with a per-call
timeout. A validator that raises is logged and skipped — never crashes
the turn. This matches the fail-open rule in the Phase 7 plan.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from gclaw.guardrails.models import (
    GuardrailResult,
    Outcome,
    Violation,
)
from gclaw.guardrails.validators import (
    LengthValidator,
    PiiValidator,
    ToxicityValidator,
    Validator,
)

logger = logging.getLogger(__name__)


@dataclass
class GuardrailProfile:
    """Named bundle of validators + per-validator severity overrides."""

    name: str
    validators: list[Validator] = field(default_factory=list)


# ── Preset profiles ───────────────────────────────────────────────────


def _strict_profile() -> GuardrailProfile:
    """Used for agents that WRITE to external systems — emails, calendar
    invites, social-media posts, PR comments. A PII slip or toxic phrase
    here is a real incident, so we BLOCK."""
    return GuardrailProfile(
        name="strict",
        validators=[
            PiiValidator(outcome_for_detect=Outcome.BLOCK),
            ToxicityValidator(outcome_for_detect=Outcome.BLOCK),
            LengthValidator(max_chars=32_000),
        ],
    )


def _loose_profile() -> GuardrailProfile:
    """Used for internal research chat — the output never leaves gclaw,
    so we WARN on PII/length rather than block the user's workflow.
    Toxicity still BLOCKs: toxic output is a real issue regardless of
    blast radius and the team shouldn't be reading it either."""
    return GuardrailProfile(
        name="loose",
        validators=[
            PiiValidator(outcome_for_detect=Outcome.WARN),
            ToxicityValidator(outcome_for_detect=Outcome.BLOCK),
            LengthValidator(max_chars=128_000),
        ],
    )


def _off_profile() -> GuardrailProfile:
    return GuardrailProfile(name="off", validators=[])


# Authority-to-profile mapping. ``AgentFactory`` (later) can override by
# name; the default reads agents/*.md tool grants to pick strict for any
# agent with external-write tools.
_DEFAULT_PROFILES: dict[str, GuardrailProfile] = {
    "strict": _strict_profile(),
    "loose": _loose_profile(),
    "off": _off_profile(),
}


# ── Service ───────────────────────────────────────────────────────────


class GuardrailService:
    """Orchestrates validator fan-out. One instance per process.

    ``enabled=False`` short-circuits to an immediate PASS result — the
    runner can install the service unconditionally and toggle via
    settings.GUARDRAILS_ENABLED.
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        default_profile: str = "loose",
        profiles: dict[str, GuardrailProfile] | None = None,
        per_validator_timeout_seconds: float = 0.2,
    ) -> None:
        self._enabled = enabled
        self._default_profile = default_profile
        self._profiles: dict[str, GuardrailProfile] = dict(_DEFAULT_PROFILES)
        if profiles:
            self._profiles.update(profiles)
        self._timeout = per_validator_timeout_seconds

    @property
    def enabled(self) -> bool:
        return self._enabled

    def resolve_profile(self, name: str | None) -> GuardrailProfile:
        if not name:
            name = self._default_profile
        return self._profiles.get(name) or self._profiles[self._default_profile]

    async def check_output(
        self,
        text: str,
        *,
        context: dict[str, Any] | None = None,
        profile: str | None = None,
    ) -> GuardrailResult:
        if not self._enabled:
            return GuardrailResult(outcome=Outcome.PASS)

        prof = self.resolve_profile(profile)
        if not prof.validators:
            return GuardrailResult(outcome=Outcome.PASS)

        start = time.perf_counter()
        violations = await self._run_all(prof.validators, text, context)
        duration = int((time.perf_counter() - start) * 1000)
        outcome = Outcome.worst([v.outcome for v in violations])
        return GuardrailResult(
            outcome=outcome, violations=violations, duration_ms=duration
        )

    async def _run_all(
        self,
        validators: list[Validator],
        text: str,
        context: dict[str, Any] | None,
    ) -> list[Violation]:
        async def _one(v: Validator) -> Violation | None:
            try:
                return await asyncio.wait_for(
                    v.check(text, context), timeout=self._timeout
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "guardrail %s timed out after %ss",
                    getattr(v, "name", "<anon>"),
                    self._timeout,
                )
                return Violation(
                    validator=getattr(v, "name", "<anon>"),
                    outcome=Outcome.WARN,
                    message="validator timed out",
                    details={"timeout_s": self._timeout},
                )
            except Exception as e:  # noqa: BLE001
                # Fail-open per plan — log + synthetic WARN, never crash.
                logger.warning(
                    "guardrail %s raised: %s",
                    getattr(v, "name", "<anon>"),
                    e,
                    exc_info=True,
                )
                return Violation(
                    validator=getattr(v, "name", "<anon>"),
                    outcome=Outcome.WARN,
                    message=f"validator raised: {e.__class__.__name__}",
                    details={"error": str(e)},
                )

        results = await asyncio.gather(*[_one(v) for v in validators])
        return [r for r in results if r is not None]
