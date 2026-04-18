"""Unit tests for the guardrail validator + service surface."""

from __future__ import annotations

import pytest

from gclaw.guardrails.models import GuardrailBlockedError, Outcome
from gclaw.guardrails.service import (
    GuardrailProfile,
    GuardrailService,
)
from gclaw.guardrails.validators import (
    GroundednessValidator,
    LengthValidator,
    PiiValidator,
    ToxicityValidator,
)


# ── Validators ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pii_validator_flags_email_and_phone():
    v = PiiValidator()
    result = await v.check("contact jane@example.com or (555) 123-4567")
    assert result is not None
    assert result.outcome == Outcome.WARN
    assert "email" in result.details["matches"]
    assert "phone" in result.details["matches"]


@pytest.mark.asyncio
async def test_pii_validator_passes_clean_text():
    v = PiiValidator()
    assert await v.check("the project is tracking well") is None


@pytest.mark.asyncio
async def test_toxicity_validator_blocks_on_match():
    v = ToxicityValidator()
    result = await v.check("please kill yourself")
    assert result is not None
    assert result.outcome == Outcome.BLOCK


@pytest.mark.asyncio
async def test_length_validator_warns_when_over_cap():
    v = LengthValidator(max_chars=100)
    result = await v.check("x" * 200)
    assert result is not None
    assert result.outcome == Outcome.WARN
    assert result.details["length"] == 200


@pytest.mark.asyncio
async def test_groundedness_validator_passes_when_score_high():
    async def judge(text: str, contexts: list[str]) -> float:
        return 0.9

    v = GroundednessValidator(judge=judge, threshold=0.6)
    assert await v.check("x", context={"retrieval": ["ctx"]}) is None


@pytest.mark.asyncio
async def test_groundedness_validator_warns_when_score_low():
    async def judge(text: str, contexts: list[str]) -> float:
        return 0.2

    v = GroundednessValidator(judge=judge, threshold=0.6)
    result = await v.check("x", context={"retrieval": ["ctx"]})
    assert result is not None
    assert result.outcome == Outcome.WARN
    assert result.details["score"] == 0.2


# ── Service orchestration ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_service_short_circuits_when_disabled():
    svc = GuardrailService(enabled=False)
    result = await svc.check_output("anything")
    assert result.outcome == Outcome.PASS
    assert result.violations == []


@pytest.mark.asyncio
async def test_service_strict_profile_blocks_pii():
    svc = GuardrailService(enabled=True, default_profile="strict")
    result = await svc.check_output("call me at (555) 123-4567")
    assert result.outcome == Outcome.BLOCK
    assert any(v.validator == "pii" for v in result.violations)


@pytest.mark.asyncio
async def test_service_loose_profile_warns_on_pii():
    svc = GuardrailService(enabled=True, default_profile="loose")
    result = await svc.check_output("call me at (555) 123-4567")
    assert result.outcome == Outcome.WARN


@pytest.mark.asyncio
async def test_service_fails_open_when_validator_raises():
    class Broken:
        name = "broken"

        async def check(self, text, context=None):
            raise RuntimeError("boom")

    prof = GuardrailProfile(name="broken", validators=[Broken()])
    svc = GuardrailService(
        enabled=True,
        default_profile="broken",
        profiles={"broken": prof},
    )
    result = await svc.check_output("anything")
    # WARN (not BLOCK) — fail-open per plan; callers shouldn't be
    # surprised by a silently-broken validator killing their turn.
    assert result.outcome == Outcome.WARN
    assert result.violations[0].message.startswith("validator raised")


@pytest.mark.asyncio
async def test_outcome_worst_wins_across_validators():
    # Mix PII (WARN in loose) + toxicity (BLOCK in defaults) — outcome is BLOCK.
    svc = GuardrailService(enabled=True, default_profile="loose")
    result = await svc.check_output(
        "kill yourself and email me at a@b.com",
    )
    assert result.outcome == Outcome.BLOCK


@pytest.mark.asyncio
async def test_blocked_error_carries_result():
    from gclaw.guardrails.models import GuardrailResult, Violation

    result = GuardrailResult(
        outcome=Outcome.BLOCK,
        violations=[
            Violation(validator="pii", outcome=Outcome.BLOCK, message="hit"),
        ],
    )
    err = GuardrailBlockedError(result)
    assert err.result is result
    assert "pii:block" in str(err)
