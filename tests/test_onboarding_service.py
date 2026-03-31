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
                current_step=OnboardingStep.COMMUNICATION_STYLE,
            )
        )

        result = await service.start_onboarding("test_user")
        assert result["step"] == "communication_style"


class TestAdvanceOnboarding:
    @pytest.mark.asyncio
    async def test_stores_response_and_advances(
        self, service, mock_agent_runner
    ):
        """Should store user response and advance to next step."""
        service._get_state = AsyncMock(
            return_value=OnboardingState(
                user_id="test_user",
                current_step=OnboardingStep.COMMUNICATION_STYLE,
            )
        )
        service._save_state = AsyncMock()

        result = await service.advance_onboarding(
            user_id="test_user",
            response="I prefer casual but concise communication.",
        )
        assert result["step"] != "communication_style"
        mock_agent_runner.run.assert_called()

    @pytest.mark.asyncio
    async def test_advance_past_final_step_triggers_soul_gen(
        self, service, mock_agent_runner, mock_memory_service
    ):
        """Advancing past the last interview step triggers soul generation."""
        service._get_state = AsyncMock(
            return_value=OnboardingState(
                user_id="test_user",
                current_step=OnboardingStep.INITIAL_CRONS,
                responses={
                    "introduction": "Hi!",
                    "communication_style": "Casual and concise",
                    "daily_routines": "Morning person, gym at 6am",
                    "professional_context": "Software engineer",
                    "personal_context": "Likes hiking",
                },
            )
        )
        service._save_state = AsyncMock()
        service._generate_soul = AsyncMock(return_value="# Soul\nCasual tone")

        result = await service.advance_onboarding(
            user_id="test_user",
            response="Set up a morning briefing at 8am.",
        )
        assert result["step"] == "complete"
        assert result["completed"] is True
        service._generate_soul.assert_called_once()


class TestGenerateSoul:
    @pytest.mark.asyncio
    async def test_sends_responses_through_orchestrator(
        self, service, mock_agent_runner
    ):
        """Soul generation sends all responses to the orchestrator."""
        mock_agent_runner.run.return_value = MagicMock(
            text="# Soul Profile\n\n- Casual communication\n- Morning person"
        )
        responses = {
            "communication_style": "Casual",
            "daily_routines": "Morning person",
            "professional_context": "Engineer",
            "personal_context": "Hiker",
        }
        soul = await service._generate_soul("test_user", responses)
        assert "Soul" in soul
        mock_agent_runner.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_captures_soul_to_memory_bank(
        self, service, mock_agent_runner, mock_memory_service
    ):
        """Generated soul should be captured to Memory Bank."""
        mock_agent_runner.run.return_value = MagicMock(
            text="# Soul\nContent"
        )
        responses = {"communication_style": "Casual"}
        await service._generate_soul("test_user", responses)
        mock_memory_service.capture.assert_called()
