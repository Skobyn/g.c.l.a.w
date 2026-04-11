"""Tests for AgentRunner.end_session — end-of-session memory extraction."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from gclaw.dispatch.runner import AgentRunner


@pytest.fixture
def mock_agent():
    agent = MagicMock()
    agent.name = "orchestrator"
    return agent


@pytest.fixture
def mock_session_service():
    svc = MagicMock()
    svc.get_session = AsyncMock(return_value=None)
    return svc


@pytest.fixture
def memory_service():
    svc = MagicMock()
    svc.generate_memories = AsyncMock(return_value=[])
    return svc


def _make_session_with_events(events: list[tuple[str, str]]):
    """Build a fake ADK session whose events have the duck-typed shape
    AgentRunner.end_session reads: event.content.role, event.content.parts[].text.
    """
    adk_events = [
        SimpleNamespace(
            content=SimpleNamespace(
                role=role,
                parts=[SimpleNamespace(text=text)],
            )
        )
        for role, text in events
    ]
    return SimpleNamespace(events=adk_events)


@pytest.mark.asyncio
async def test_end_session_with_memory(mock_agent, mock_session_service, memory_service):
    fake_session = _make_session_with_events([
        ("user", "I prefer terse responses"),
        ("model", "Got it."),
    ])
    mock_session_service.get_session = AsyncMock(return_value=fake_session)

    runner = AgentRunner(
        agent=mock_agent,
        app_name="gclaw",
        session_service=mock_session_service,
        memory_service=memory_service,
    )

    await runner.end_session(user_id="user_123", session_id="sess_1")

    memory_service.generate_memories.assert_awaited_once()
    kwargs = memory_service.generate_memories.call_args.kwargs
    assert kwargs["user_id"] == "user_123"
    assert "User: I prefer terse responses" in kwargs["conversation_text"]
    assert "Agent: Got it." in kwargs["conversation_text"]


@pytest.mark.asyncio
async def test_end_session_without_memory(mock_agent, mock_session_service):
    runner = AgentRunner(
        agent=mock_agent,
        app_name="gclaw",
        session_service=mock_session_service,
        memory_service=None,
    )
    # Should be a no-op; should not touch session_service either.
    await runner.end_session(user_id="user_123", session_id="sess_1")
    mock_session_service.get_session.assert_not_called()


@pytest.mark.asyncio
async def test_end_session_session_missing(mock_agent, mock_session_service, memory_service):
    mock_session_service.get_session = AsyncMock(return_value=None)
    runner = AgentRunner(
        agent=mock_agent,
        app_name="gclaw",
        session_service=mock_session_service,
        memory_service=memory_service,
    )
    await runner.end_session(user_id="user_123", session_id="sess_1")
    memory_service.generate_memories.assert_not_awaited()


@pytest.mark.asyncio
async def test_end_session_empty_transcript(mock_agent, mock_session_service, memory_service):
    fake_session = _make_session_with_events([])
    mock_session_service.get_session = AsyncMock(return_value=fake_session)
    runner = AgentRunner(
        agent=mock_agent,
        app_name="gclaw",
        session_service=mock_session_service,
        memory_service=memory_service,
    )
    await runner.end_session(user_id="user_123", session_id="sess_1")
    memory_service.generate_memories.assert_not_awaited()


@pytest.mark.asyncio
async def test_end_session_get_session_error_swallowed(
    mock_agent, mock_session_service, memory_service
):
    mock_session_service.get_session = AsyncMock(side_effect=RuntimeError("boom"))
    runner = AgentRunner(
        agent=mock_agent,
        app_name="gclaw",
        session_service=mock_session_service,
        memory_service=memory_service,
    )
    # Should not raise.
    await runner.end_session(user_id="user_123", session_id="sess_1")
    memory_service.generate_memories.assert_not_awaited()


@pytest.mark.asyncio
async def test_end_session_memory_failure_swallowed(
    mock_agent, mock_session_service, memory_service
):
    fake_session = _make_session_with_events([("user", "hello")])
    mock_session_service.get_session = AsyncMock(return_value=fake_session)
    memory_service.generate_memories = AsyncMock(side_effect=RuntimeError("mem bank down"))

    runner = AgentRunner(
        agent=mock_agent,
        app_name="gclaw",
        session_service=mock_session_service,
        memory_service=memory_service,
    )
    # Should not raise.
    await runner.end_session(user_id="user_123", session_id="sess_1")
    memory_service.generate_memories.assert_awaited_once()


@pytest.mark.asyncio
async def test_end_session_delegates_to_session_store(
    mock_agent, mock_session_service, memory_service
):
    """When a session_store is configured, end_session delegates to it
    and skips the ADK-transcript fallback path."""
    session_store = MagicMock()
    session_store.end_session = AsyncMock(return_value=None)

    runner = AgentRunner(
        agent=mock_agent,
        app_name="gclaw",
        session_service=mock_session_service,
        memory_service=memory_service,
        session_store=session_store,
    )

    await runner.end_session(user_id="user_123", session_id="sess_1")

    session_store.end_session.assert_awaited_once_with("sess_1")
    # ADK fallback path must NOT run when session_store is set.
    mock_session_service.get_session.assert_not_called()
    memory_service.generate_memories.assert_not_awaited()


@pytest.mark.asyncio
async def test_end_session_store_failure_swallowed(
    mock_agent, mock_session_service, memory_service
):
    session_store = MagicMock()
    session_store.end_session = AsyncMock(side_effect=RuntimeError("firestore down"))

    runner = AgentRunner(
        agent=mock_agent,
        app_name="gclaw",
        session_service=mock_session_service,
        memory_service=memory_service,
        session_store=session_store,
    )

    # Should not raise.
    await runner.end_session(user_id="user_123", session_id="sess_1")
    session_store.end_session.assert_awaited_once()
