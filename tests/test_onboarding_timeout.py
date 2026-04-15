"""Tests that OnboardingService enforces a per-turn timeout.

The real fix addresses the Cloud Run hang observed when Vertex AI
returns 429 RESOURCE_EXHAUSTED and the AgentRunner can't retry: the
route handler must not block forever.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from gclaw.onboarding.service import OnboardingService


@pytest.fixture
def mock_db():
    db = MagicMock()
    doc_mock = MagicMock()
    doc_mock.exists = False
    db.collection.return_value.document.return_value.get.return_value = doc_mock
    return db


def _make_service(db, agent_runner, timeout_s: float) -> OnboardingService:
    return OnboardingService(
        db=db,
        agent_runner=agent_runner,
        memory_service=None,
        turn_timeout_s=timeout_s,
    )


@pytest.mark.asyncio
async def test_start_onboarding_raises_runtime_error_on_timeout(mock_db):
    """If the agent hangs, start_onboarding raises RuntimeError in <1s."""
    agent_runner = MagicMock()

    async def hang(**kwargs):
        await asyncio.sleep(120)  # pragma: no cover
        return MagicMock(text="should never reach here")

    agent_runner.run = hang

    service = _make_service(mock_db, agent_runner, timeout_s=0.2)

    loop = asyncio.get_event_loop()
    t0 = loop.time()
    with pytest.raises(RuntimeError, match="timed out"):
        await service.start_onboarding("user1")
    elapsed = loop.time() - t0
    # Should fail near the timeout, well under a second.
    assert elapsed < 1.0


@pytest.mark.asyncio
async def test_advance_onboarding_raises_runtime_error_on_timeout(mock_db):
    """Existing user, next turn hangs → RuntimeError from advance()."""
    # Make Firestore report an in-progress onboarding state so advance()
    # goes to the agent_runner path instead of start_onboarding().
    from gclaw.models.onboarding import OnboardingState, OnboardingStep
    state = OnboardingState(
        user_id="user1", current_step=OnboardingStep.INTRODUCTION,
    )
    doc_mock = MagicMock()
    doc_mock.exists = True
    doc_mock.to_dict.return_value = {"onboarding": state.to_firestore_dict()}
    mock_db.collection.return_value.document.return_value.get.return_value = doc_mock

    agent_runner = MagicMock()

    async def hang(**kwargs):
        await asyncio.sleep(120)  # pragma: no cover
        return MagicMock(text="should never reach here")

    agent_runner.run = hang

    service = _make_service(mock_db, agent_runner, timeout_s=0.2)

    with pytest.raises(RuntimeError, match="timed out"):
        await service.advance_onboarding(user_id="user1", response="sure")


@pytest.mark.asyncio
async def test_start_onboarding_succeeds_within_timeout(mock_db):
    """Happy path — fast response, no timeout triggered."""
    agent_runner = AsyncMock()
    agent_runner.run.return_value = MagicMock(text="Hi, I'm GClaw!")

    service = _make_service(mock_db, agent_runner, timeout_s=5.0)

    result = await service.start_onboarding("user1")
    assert result["completed"] is False
    assert result["message"] == "Hi, I'm GClaw!"
    assert result["step"] == "introduction"
