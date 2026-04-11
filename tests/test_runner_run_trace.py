"""Tests for AgentRunner.run_trace — the eval-only variant of run()."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from gclaw.dispatch.runner import AgentRunner


@pytest.fixture
def mock_agent():
    agent = MagicMock()
    agent.name = "orchestrator"
    return agent


@pytest.fixture
def mock_session_service():
    from unittest.mock import AsyncMock
    svc = MagicMock()
    svc.get_session = AsyncMock(return_value=MagicMock())
    return svc


def _stub_adk_stream(runner, *, raise_after: int | None = None):
    """Stub the inner ADK runner's event stream.

    Emits three events: a function_call, a text part, then a final.
    If `raise_after` is set, raises RuntimeError after emitting that
    many events.
    """
    events = []

    def _make_event(text=None, function_call=None, final=False):
        ev = MagicMock()
        ev.content = MagicMock()
        parts = []
        if text is not None:
            parts.append(MagicMock(text=text, function_call=None))
        if function_call is not None:
            fc = MagicMock()
            fc.name = function_call
            fc.args = {}
            parts.append(MagicMock(text=None, function_call=fc))
        ev.content.parts = parts
        ev.is_final_response.return_value = final
        return ev

    events.append(_make_event(function_call="create_board_task"))
    events.append(_make_event(text="done"))
    events.append(_make_event(final=True))

    async def _stream(**kwargs):
        for i, ev in enumerate(events):
            if raise_after is not None and i == raise_after:
                raise RuntimeError("simulated mid-stream failure")
            yield ev

    runner._runner = MagicMock()
    runner._runner.run_async = _stream


@pytest.mark.asyncio
async def test_run_trace_returns_response_and_no_error_on_clean_run(
    mock_agent, mock_session_service
):
    runner = AgentRunner(
        agent=mock_agent,
        app_name="gclaw",
        session_service=mock_session_service,
    )
    _stub_adk_stream(runner)

    response, error = await runner.run_trace(
        user_id="eval_user", session_id="eval_0", message="create a task"
    )

    assert error is None
    assert response.text == "done"
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0]["name"] == "create_board_task"
    assert response.is_final is True


@pytest.mark.asyncio
async def test_run_trace_preserves_tool_calls_on_mid_stream_exception(
    mock_agent, mock_session_service
):
    """The whole point of run_trace: tool_calls captured before the
    failure must survive into the returned response."""
    runner = AgentRunner(
        agent=mock_agent,
        app_name="gclaw",
        session_service=mock_session_service,
    )
    _stub_adk_stream(runner, raise_after=1)  # raise after function_call but before final

    response, error = await runner.run_trace(
        user_id="eval_user", session_id="eval_0", message="create a task"
    )

    assert error is not None
    assert "simulated" in error
    # Tool call captured BEFORE the exception is preserved.
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0]["name"] == "create_board_task"


@pytest.mark.asyncio
async def test_run_trace_sets_active_user_on_board_and_session_store(
    mock_agent, mock_session_service
):
    """Regression: run_trace must call set_active_user on board_service
    and session_store exactly like run() does, so tools fired during
    the eval get a valid user context. This was broken in the first
    live eval run and surfaced as 'user_id required — not set at init
    or in method call' errors on all three board cases."""
    board_service = MagicMock()
    session_store = MagicMock()

    runner = AgentRunner(
        agent=mock_agent,
        app_name="gclaw",
        session_service=mock_session_service,
        board_service=board_service,
        session_store=session_store,
    )
    _stub_adk_stream(runner)

    await runner.run_trace(
        user_id="eval_user", session_id="eval_0", message="ping"
    )

    board_service.set_active_user.assert_called_once_with("eval_user")
    session_store.set_active_user.assert_called_once_with("eval_user")
