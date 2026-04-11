"""Tests for AgentRunner session_store mirroring.

When a persistent SessionService is wired as session_store, each turn
should be mirrored into it so transcripts survive process restarts and
end-of-session extraction has a durable source.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from gclaw.dispatch.runner import AgentRunner


@pytest.fixture
def mock_agent():
    agent = MagicMock()
    agent.name = "orchestrator"
    return agent


@pytest.fixture
def mock_session_service():
    return MagicMock()


def _patch_adk_runner(runner):
    """Stub ADK's inner Runner to return a single text event."""
    mock_event = MagicMock()
    mock_event.content = MagicMock()
    mock_event.content.parts = [MagicMock(text="pong", function_call=None)]
    mock_event.is_final_response.return_value = True

    async def mock_run_async(**kwargs):
        yield mock_event

    runner._runner = MagicMock()
    runner._runner.run_async = mock_run_async


@pytest.mark.asyncio
async def test_session_store_receives_user_and_agent_messages(
    mock_agent, mock_session_service
):
    session_store = MagicMock()
    session_store.get_or_none.return_value = MagicMock()  # session exists
    session_store.append_message.return_value = None

    runner = AgentRunner(
        agent=mock_agent,
        app_name="gclaw",
        session_service=mock_session_service,
        session_store=session_store,
    )
    _patch_adk_runner(runner)

    await runner.run(user_id="u1", session_id="sess_1", message="ping")

    # Session lookup happened, no create call needed.
    session_store.get_or_none.assert_called_once_with("sess_1")
    session_store.create_with_id.assert_not_called()

    # Two appends: user then agent.
    assert session_store.append_message.call_count == 2
    calls = session_store.append_message.call_args_list
    assert calls[0].kwargs == {
        "session_id": "sess_1",
        "role": "user",
        "content": "ping",
    }
    assert calls[1].kwargs == {
        "session_id": "sess_1",
        "role": "agent",
        "content": "pong",
    }


@pytest.mark.asyncio
async def test_session_store_creates_missing_session(
    mock_agent, mock_session_service
):
    session_store = MagicMock()
    session_store.get_or_none.return_value = None  # not yet in store

    runner = AgentRunner(
        agent=mock_agent,
        app_name="gclaw",
        session_service=mock_session_service,
        session_store=session_store,
    )
    _patch_adk_runner(runner)

    await runner.run(user_id="u1", session_id="sess_new", message="hi")

    session_store.create_with_id.assert_called_once_with(
        session_id="sess_new", user_id="u1"
    )
    assert session_store.append_message.call_count == 2


@pytest.mark.asyncio
async def test_session_store_mirror_failure_does_not_break_run(
    mock_agent, mock_session_service
):
    session_store = MagicMock()
    session_store.get_or_none.side_effect = RuntimeError("firestore down")

    runner = AgentRunner(
        agent=mock_agent,
        app_name="gclaw",
        session_service=mock_session_service,
        session_store=session_store,
    )
    _patch_adk_runner(runner)

    # Must not raise.
    response = await runner.run(user_id="u1", session_id="sess_1", message="hi")
    assert response.text == "pong"


@pytest.mark.asyncio
async def test_no_session_store_is_noop(mock_agent, mock_session_service):
    runner = AgentRunner(
        agent=mock_agent,
        app_name="gclaw",
        session_service=mock_session_service,
        session_store=None,
    )
    _patch_adk_runner(runner)

    # Should run without any session_store interaction.
    response = await runner.run(user_id="u1", session_id="sess_1", message="hi")
    assert response.text == "pong"
