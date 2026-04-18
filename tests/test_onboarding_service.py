"""Tests for the OnboardingService."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from gclaw.models.onboarding import OnboardingState, OnboardingStep
from gclaw.onboarding.service import OnboardingService


@pytest.fixture
def mock_db():
    db = MagicMock()
    # Default: no document exists in Firestore
    doc_mock = MagicMock()
    doc_mock.exists = False
    db.collection.return_value.document.return_value.get.return_value = doc_mock
    return db


@pytest.fixture
def mock_agent_runner():
    runner = AsyncMock()
    runner.run.return_value = MagicMock(
        text="Tell me about your communication preferences."
    )
    return runner


@pytest.fixture
def mock_memory_service():
    return AsyncMock()


@pytest.fixture
def service(mock_db, mock_agent_runner, mock_memory_service):
    return OnboardingService(
        db=mock_db,
        agent_runner=mock_agent_runner,
        memory_service=mock_memory_service,
    )


class TestOnboardingState:
    def test_initial_state(self):
        state = OnboardingState(user_id="test_user")
        assert state.current_step == OnboardingStep.INTRODUCTION
        assert state.completed is False
        assert state.responses == {}

    def test_step_progression(self):
        """Steps follow the defined interview sequence."""
        steps = list(OnboardingStep)
        assert steps[0] == OnboardingStep.INTRODUCTION
        assert steps[-1] == OnboardingStep.COMPLETE


class TestStartOnboarding:
    @pytest.mark.asyncio
    async def test_creates_initial_state(self, service, mock_db):
        """Should create an onboarding state record and return intro message."""
        result = await service.start_onboarding("test_user")
        assert result["step"] == "introduction"
        assert "message" in result

    @pytest.mark.asyncio
    async def test_idempotent_if_already_started(self, service, mock_db):
        """Should return current state if onboarding already in progress."""
        # Mock existing state
        service._get_state = AsyncMock(
            return_value=OnboardingState(
                user_id="test_user",
                current_step=OnboardingStep.Q1_IDENTITY,
            )
        )

        result = await service.start_onboarding("test_user")
        assert result["step"] == "q1_identity"


class TestAdvanceOnboarding:
    @pytest.mark.asyncio
    async def test_stores_response_and_advances(
        self, service, mock_agent_runner
    ):
        """Should store user response and advance to next step."""
        service._get_state = AsyncMock(
            return_value=OnboardingState(
                user_id="test_user",
                current_step=OnboardingStep.Q1_IDENTITY,
            )
        )
        service._save_state = AsyncMock()

        result = await service.advance_onboarding(
            user_id="test_user",
            response="Call me Scott, I run a small product team.",
        )
        assert result["step"] != "q1_identity"
        mock_agent_runner.run.assert_called()

    @pytest.mark.asyncio
    async def test_advance_past_final_step_triggers_profile_gen(
        self, service, mock_agent_runner, mock_memory_service
    ):
        """Advancing past the last interview step triggers profile generation."""
        service._get_state = AsyncMock(
            return_value=OnboardingState(
                user_id="test_user",
                current_step=OnboardingStep.Q10_LATENT_WISH,
                responses={
                    "introduction": "Hi!",
                    "q1_identity": "Scott, product lead",
                    "q2_chronotype": "Morning, US/Central",
                    "q3_detail_level": "Bottom line first",
                    "q4_directness": "Blunt",
                    "q5_autonomy": "4 — mostly just do it",
                    "q6_interrupts": "Queue unless truly urgent",
                    "q7_disagreement": "Point it out",
                    "q8_current_focus": "Launch v1",
                    "q9_hard_nos": "No flowery prose",
                },
            )
        )
        service._save_state = AsyncMock()
        service._generate_user_profile = AsyncMock(
            return_value="## Identity\nScott, product lead"
        )

        result = await service.advance_onboarding(
            user_id="test_user",
            response="I wish you'd proactively clear my inbox each morning.",
        )
        assert result["step"] == "complete"
        assert result["completed"] is True
        service._generate_user_profile.assert_called_once()


class TestGenerateUserProfile:
    @pytest.mark.asyncio
    async def test_sends_responses_through_orchestrator(
        self, service, mock_agent_runner
    ):
        """Profile generation sends all responses to the orchestrator."""
        mock_agent_runner.run.return_value = MagicMock(
            text="## Identity\n\nScott, product lead\n\n## Working style\nMorning, US/Central"
        )
        responses = {
            "q1_identity": "Scott, product lead",
            "q2_chronotype": "Morning, US/Central",
            "q3_detail_level": "Bottom line first",
            "q4_directness": "Blunt",
        }
        profile = await service._generate_user_profile("test_user", responses)
        assert "Identity" in profile
        mock_agent_runner.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_captures_profile_to_memory_bank(
        self, service, mock_agent_runner, mock_memory_service
    ):
        """Generated profile should be captured to Memory Bank."""
        mock_agent_runner.run.return_value = MagicMock(
            text="## Identity\nContent"
        )
        responses = {"q1_identity": "Scott, product lead"}
        await service._generate_user_profile("test_user", responses)
        mock_memory_service.capture.assert_called()
