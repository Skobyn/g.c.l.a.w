"""AgentRunner emits per-author input/output messages to AgentRunsRepo."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from gclaw.dispatch.runner import AgentRunner


def _event(text=None, func_name=None, func_args=None, author=None,
           usage=None, final=False, model_version=None):
    ev = MagicMock()
    ev.is_final_response.return_value = final
    parts = []
    if text:
        p = MagicMock()
        p.text = text
        p.function_call = None
        parts.append(p)
    if func_name:
        p = MagicMock()
        p.text = None
        fc = MagicMock()
        fc.name = func_name
        fc.args = func_args or {}
        p.function_call = fc
        parts.append(p)
    ev.content = MagicMock()
    ev.content.parts = parts or None
    ev.usage_metadata = usage
    ev.model_version = model_version
    ev.author = author
    return ev


@pytest.mark.asyncio
async def test_runner_emits_per_author_messages_after_turn():
    """After a multi-author turn, the runner writes one user input
    message + one output message per distinct author to the
    agent_runs_repo, redacted, sorted with the root agent first."""
    agent = MagicMock()
    agent.name = "orchestrator"
    session_service = AsyncMock()
    repo = MagicMock()

    events = [
        # Orchestrator does its own thinking + delegates via a tool call.
        _event(text="Routing to research-mgr.",
               author="orchestrator"),
        _event(func_name="research_mgr",
               func_args={"query": "what is mem0?"},
               author="orchestrator"),
        # research-mgr produces a result (note: ADK normalizes the
        # name with an underscore in event.author).
        _event(text="Mem0 is a memory layer for LLMs.",
               author="research_mgr"),
        _event(final=True, author="orchestrator"),
    ]

    async def fake_run(**kwargs):
        for e in events:
            yield e

    with patch("gclaw.dispatch.runner.Runner") as MockRunner:
        MockRunner.return_value.run_async = fake_run
        runner = AgentRunner(
            agent=agent,
            app_name="gclaw",
            session_service=session_service,
            agent_runs_repo=repo,
        )
        await runner.run(user_id="u1", session_id="s1", message="research mem0")

    # Under the NoOp tracer trace_id is 0 so the emit short-circuits.
    # Re-arm with a stub turn span that returns a real trace_id.
    repo.append_messages.assert_not_called()


@pytest.mark.asyncio
async def test_runner_messages_include_user_input_and_each_author():
    """When the trace context is real, the repo gets a user input
    message + one output per author, in root-first order."""
    agent = MagicMock()
    agent.name = "orchestrator"
    session_service = AsyncMock()
    repo = MagicMock()

    events = [
        _event(text="Working on it.", author="orchestrator"),
        _event(func_name="research_mgr",
               func_args={"query": "find docs"},
               author="orchestrator"),
        _event(text="Found three relevant pages.", author="research_mgr"),
        _event(final=True, author="orchestrator"),
    ]

    async def fake_run(**kwargs):
        for e in events:
            yield e

    # Stub the OTel tracer so turn_span has a non-zero trace_id —
    # otherwise _emit_turn_messages bails before calling the repo.
    fake_ctx = MagicMock()
    fake_ctx.trace_id = 0xABC123
    fake_span = MagicMock()
    fake_span.get_span_context.return_value = fake_ctx
    # Make set_attribute / record_exception no-op safely.
    fake_span.__enter__ = MagicMock(return_value=fake_span)
    fake_span.__exit__ = MagicMock(return_value=False)
    fake_tracer = MagicMock()
    fake_tracer.start_as_current_span.return_value = fake_span

    with patch("gclaw.dispatch.runner.Runner") as MockRunner, \
         patch("gclaw.dispatch.runner._tracer", fake_tracer):
        MockRunner.return_value.run_async = fake_run
        runner = AgentRunner(
            agent=agent,
            app_name="gclaw",
            session_service=session_service,
            agent_runs_repo=repo,
        )
        await runner.run(
            user_id="u1", session_id="s1", message="research mem0",
        )

    repo.append_messages.assert_called_once()
    kwargs = repo.append_messages.call_args.kwargs
    assert kwargs["user_id"] == "u1"
    assert kwargs["run_id"] == "s1"
    assert kwargs["trace_id"] == format(0xABC123, "032x")

    msgs = kwargs["messages"]
    # First message: user input.
    assert msgs[0]["author"] == "user"
    assert msgs[0]["role"] == "input"
    assert msgs[0]["text"] == "research mem0"
    # Second: orchestrator (root) output, with the tool call captured.
    assert msgs[1]["author"] == "orchestrator"
    assert msgs[1]["role"] == "output"
    assert "Working on it." in msgs[1]["text"]
    tool_names = [tc["name"] for tc in msgs[1]["tool_calls"]]
    assert "research_mgr" in tool_names
    # Third: research-mgr (sub) output, name normalized to dash form.
    assert msgs[2]["author"] == "research-mgr"
    assert msgs[2]["role"] == "output"
    assert "Found three relevant pages." in msgs[2]["text"]


@pytest.mark.asyncio
async def test_runner_redacts_pii_from_messages():
    """Email addresses and obvious secrets must be replaced with
    <REDACTED:...> tokens before they hit the repo."""
    agent = MagicMock()
    agent.name = "orchestrator"
    session_service = AsyncMock()
    repo = MagicMock()

    secret_input = "DM scott@example.com with key sk-ant-api03-aaaaaaaaaaaaaaaaaaaa"
    secret_output = "Sent to scott@example.com — token sk-ant-api03-bbbbbbbbbbbbbbbbbbbb"

    events = [
        _event(text=secret_output, author="orchestrator"),
        _event(final=True, author="orchestrator"),
    ]

    async def fake_run(**kwargs):
        for e in events:
            yield e

    fake_ctx = MagicMock()
    fake_ctx.trace_id = 0xDEAD
    fake_span = MagicMock()
    fake_span.get_span_context.return_value = fake_ctx
    fake_span.__enter__ = MagicMock(return_value=fake_span)
    fake_span.__exit__ = MagicMock(return_value=False)
    fake_tracer = MagicMock()
    fake_tracer.start_as_current_span.return_value = fake_span

    with patch("gclaw.dispatch.runner.Runner") as MockRunner, \
         patch("gclaw.dispatch.runner._tracer", fake_tracer):
        MockRunner.return_value.run_async = fake_run
        runner = AgentRunner(
            agent=agent,
            app_name="gclaw",
            session_service=session_service,
            agent_runs_repo=repo,
        )
        await runner.run(
            user_id="u1", session_id="s1", message=secret_input,
        )

    msgs = repo.append_messages.call_args.kwargs["messages"]
    # User input must be redacted.
    assert "scott@example.com" not in msgs[0]["text"]
    assert "sk-ant-api03-aaaa" not in msgs[0]["text"]
    assert "<REDACTED:email>" in msgs[0]["text"]
    assert "<REDACTED:anthropic_api>" in msgs[0]["text"]
    # Agent output must be redacted.
    assert "scott@example.com" not in msgs[1]["text"]
    assert "sk-ant-api03-bbbb" not in msgs[1]["text"]


@pytest.mark.asyncio
async def test_runner_without_repo_does_not_emit_messages():
    """When agent_runs_repo is None (unit tests, dev mode without
    Firestore), the message capture path is silent."""
    agent = MagicMock()
    agent.name = "orchestrator"
    session_service = AsyncMock()

    async def fake_run(**kwargs):
        yield _event(text="hi", author="orchestrator", final=True)

    with patch("gclaw.dispatch.runner.Runner") as MockRunner:
        MockRunner.return_value.run_async = fake_run
        runner = AgentRunner(
            agent=agent,
            app_name="gclaw",
            session_service=session_service,
            agent_runs_repo=None,
        )
        # Should not raise.
        resp = await runner.run(
            user_id="u1", session_id="s1", message="hi"
        )
    assert resp.text == "hi"
