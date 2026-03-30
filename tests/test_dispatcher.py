"""Tests for agent runner."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from gclaw.dispatch.runner import AgentRunner, AgentResponse


def test_runner_init():
    agent = MagicMock()
    agent.name = "orchestrator"
    runner = AgentRunner(
        agent=agent,
        app_name="gclaw",
        session_service=AsyncMock(),
    )
    assert runner._agent.name == "orchestrator"
    assert runner._app_name == "gclaw"


@pytest.mark.asyncio
async def test_runner_run_collects_text():
    agent = MagicMock()
    agent.name = "orchestrator"
    session_service = AsyncMock()

    runner = AgentRunner(
        agent=agent,
        app_name="gclaw",
        session_service=session_service,
    )

    # Mock the ADK Runner
    mock_event = MagicMock()
    mock_event.is_final_response.return_value = True
    mock_part = MagicMock()
    mock_part.text = "Hello! How can I help?"
    mock_part.function_call = None
    mock_event.content = MagicMock()
    mock_event.content.parts = [mock_part]

    async def fake_run(**kwargs):
        yield mock_event

    with patch("gclaw.dispatch.runner.Runner") as MockRunner:
        instance = MockRunner.return_value
        instance.run_async = fake_run

        # Need to re-create runner so it picks up the mocked Runner
        runner = AgentRunner(
            agent=agent,
            app_name="gclaw",
            session_service=session_service,
        )

        response = await runner.run(
            user_id="user_1",
            session_id="session_123",
            message="Hello",
        )

    assert response.text == "Hello! How can I help?"
    assert response.is_final is True
