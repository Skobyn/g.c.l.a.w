"""Tests for AgentRunner memory integration.

Tests that the runner performs auto-recall before a turn and
auto-capture after a turn when a MemoryService is provided.
"""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from gclaw.models.memory import Memory
from gclaw.dispatch.runner import AgentRunner, AgentResponse


@pytest.fixture
def mock_agent():
    agent = MagicMock()
    agent.name = "orchestrator"
    return agent


@pytest.fixture
def mock_session_service():
    return MagicMock()


@pytest.fixture
def memory_service():
    svc = MagicMock()
    svc.recall = AsyncMock(return_value=[
        Memory(fact="User prefers concise answers", topic="USER_PREFERENCES"),
    ])
    svc.capture = AsyncMock(return_value=[])
    svc.format_for_prompt = MagicMock(return_value="- User prefers concise answers")
    return svc


@pytest.fixture
def runner_with_memory(mock_agent, mock_session_service, memory_service):
    runner = AgentRunner(
        agent=mock_agent,
        app_name="gclaw",
        session_service=mock_session_service,
        memory_service=memory_service,
    )
    return runner


@pytest.fixture
def runner_without_memory(mock_agent, mock_session_service):
    runner = AgentRunner(
        agent=mock_agent,
        app_name="gclaw",
        session_service=mock_session_service,
    )
    return runner


@pytest.mark.asyncio
async def test_run_with_memory_recall(runner_with_memory, memory_service):
    """Memory recall is called before the agent turn."""
    # Mock the internal runner to return a simple response
    mock_event = MagicMock()
    mock_event.content = MagicMock()
    mock_event.content.parts = [MagicMock(text="Hello!", function_call=None)]
    mock_event.is_final_response.return_value = True

    async def mock_run_async(**kwargs):
        yield mock_event

    runner_with_memory._runner = MagicMock()
    runner_with_memory._runner.run_async = mock_run_async

    response = await runner_with_memory.run(
        user_id="user_123",
        session_id="sess_1",
        message="What are my preferences?",
    )

    memory_service.recall.assert_awaited_once_with(
        user_id="user_123",
        query="What are my preferences?",
        agent_id="orchestrator",
        merge_user_scope=True,
    )


@pytest.mark.asyncio
async def test_run_with_memory_capture(runner_with_memory, memory_service):
    """Memory capture is scheduled as a background task after the agent turn."""
    mock_event = MagicMock()
    mock_event.content = MagicMock()
    mock_event.content.parts = [MagicMock(text="Your preference is dark mode.", function_call=None)]
    mock_event.is_final_response.return_value = True

    async def mock_run_async(**kwargs):
        yield mock_event

    runner_with_memory._runner = MagicMock()
    runner_with_memory._runner.run_async = mock_run_async

    response = await runner_with_memory.run(
        user_id="user_123",
        session_id="sess_1",
        message="I prefer dark mode",
    )

    # run() returned; capture was scheduled as a background task and is
    # tracked in _pending_captures to avoid GC.
    assert response.text == "Your preference is dark mode."
    assert len(runner_with_memory._pending_captures) == 1

    # Let the background task run to completion, then verify capture was invoked.
    pending = list(runner_with_memory._pending_captures)
    await asyncio.gather(*pending)

    memory_service.capture.assert_awaited_once()
    call_kwargs = memory_service.capture.call_args.kwargs
    assert call_kwargs["user_id"] == "user_123"
    assert "I prefer dark mode" in call_kwargs["conversation_text"]
    assert "Your preference is dark mode." in call_kwargs["conversation_text"]


@pytest.mark.asyncio
async def test_run_without_memory(runner_without_memory):
    """Runner works fine without memory service."""
    mock_event = MagicMock()
    mock_event.content = MagicMock()
    mock_event.content.parts = [MagicMock(text="Hello!", function_call=None)]
    mock_event.is_final_response.return_value = True

    async def mock_run_async(**kwargs):
        yield mock_event

    runner_without_memory._runner = MagicMock()
    runner_without_memory._runner.run_async = mock_run_async

    response = await runner_without_memory.run(
        user_id="user_123",
        session_id="sess_1",
        message="Hello",
    )

    assert response.text == "Hello!"


@pytest.mark.asyncio
async def test_capture_passes_default_extraction_topics(mock_agent, mock_session_service, memory_service):
    """Item 4: AgentRunner.run background-captures with the full
    DEFAULT_EXTRACTION_TOPICS list so Memory Bank gets structured
    category guidance on every turn."""
    from gclaw.models.memory import DEFAULT_EXTRACTION_TOPICS

    runner = AgentRunner(
        agent=mock_agent,
        app_name="gclaw",
        session_service=mock_session_service,
        memory_service=memory_service,
    )

    mock_event = MagicMock()
    mock_event.content = MagicMock()
    mock_event.content.parts = [MagicMock(text="hi back", function_call=None)]
    mock_event.is_final_response.return_value = True

    async def mock_run_async(**kwargs):
        yield mock_event

    runner._runner = MagicMock()
    runner._runner.run_async = mock_run_async

    await runner.run(user_id="u1", session_id="s1", message="hi")

    # Flush the background capture task.
    await asyncio.gather(*runner._pending_captures)

    memory_service.capture.assert_awaited_once()
    kwargs = memory_service.capture.call_args.kwargs
    assert kwargs["topics"] == DEFAULT_EXTRACTION_TOPICS


@pytest.mark.asyncio
async def test_capture_accepts_custom_topic_override(mock_agent, mock_session_service, memory_service):
    """Callers can override DEFAULT_EXTRACTION_TOPICS via the
    constructor — useful for tests and lean capture paths."""
    runner = AgentRunner(
        agent=mock_agent,
        app_name="gclaw",
        session_service=mock_session_service,
        memory_service=memory_service,
        extraction_topics=["USER_PREFERENCES"],
    )

    mock_event = MagicMock()
    mock_event.content = MagicMock()
    mock_event.content.parts = [MagicMock(text="ok", function_call=None)]
    mock_event.is_final_response.return_value = True

    async def mock_run_async(**kwargs):
        yield mock_event

    runner._runner = MagicMock()
    runner._runner.run_async = mock_run_async

    await runner.run(user_id="u1", session_id="s1", message="hi")
    await asyncio.gather(*runner._pending_captures)

    assert memory_service.capture.call_args.kwargs["topics"] == ["USER_PREFERENCES"]


@pytest.mark.asyncio
async def test_capture_empty_topics_opts_out(mock_agent, mock_session_service, memory_service):
    """Passing extraction_topics=[] sends topics=None to capture —
    lets Memory Bank pick its own defaults rather than steering."""
    runner = AgentRunner(
        agent=mock_agent,
        app_name="gclaw",
        session_service=mock_session_service,
        memory_service=memory_service,
        extraction_topics=[],
    )

    mock_event = MagicMock()
    mock_event.content = MagicMock()
    mock_event.content.parts = [MagicMock(text="ok", function_call=None)]
    mock_event.is_final_response.return_value = True

    async def mock_run_async(**kwargs):
        yield mock_event

    runner._runner = MagicMock()
    runner._runner.run_async = mock_run_async

    await runner.run(user_id="u1", session_id="s1", message="hi")
    await asyncio.gather(*runner._pending_captures)

    assert memory_service.capture.call_args.kwargs["topics"] is None


@pytest.mark.asyncio
async def test_memory_failure_does_not_break_run(runner_with_memory, memory_service):
    """If memory operations fail, the agent turn still succeeds."""
    memory_service.recall.side_effect = Exception("Memory Bank unavailable")

    mock_event = MagicMock()
    mock_event.content = MagicMock()
    mock_event.content.parts = [MagicMock(text="Hello!", function_call=None)]
    mock_event.is_final_response.return_value = True

    async def mock_run_async(**kwargs):
        yield mock_event

    runner_with_memory._runner = MagicMock()
    runner_with_memory._runner.run_async = mock_run_async

    # Should not raise even though recall failed
    response = await runner_with_memory.run(
        user_id="user_123",
        session_id="sess_1",
        message="Hello",
    )

    assert response.text == "Hello!"
