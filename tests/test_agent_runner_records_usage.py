"""AgentRunner emits usage events for agent invoke, model call, and tool calls."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from gclaw.dispatch.runner import AgentRunner
from gclaw.usage.recorder import UsageRecorder


def _event(text=None, func_name=None, func_args=None, usage=None,
           final=False, model_version=None):
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
    return ev


@pytest.mark.asyncio
async def test_runner_records_agent_model_and_tools():
    agent = MagicMock()
    agent.name = "orchestrator"
    session_service = AsyncMock()

    repo = MagicMock()
    recorder = UsageRecorder(repo=repo, enabled=True)

    usage_meta = MagicMock()
    usage_meta.prompt_token_count = 100
    usage_meta.candidates_token_count = 25

    events = [
        _event(text="hello", usage=usage_meta, model_version="gemini-2.5-flash"),
        _event(func_name="create_board_task", func_args={"title": "x"}),
        _event(final=True),
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
            usage_recorder=recorder,
        )
        await runner.run(user_id="u1", session_id="s1", message="hi")

    kinds = [call.args[0].kind.value for call in repo.record.call_args_list]
    # Must have exactly one agent invoke, one model call, and one tool call
    assert kinds.count("agent") == 1
    assert kinds.count("model") == 1
    assert kinds.count("tool") == 1

    records = {c.args[0].kind.value: c.args[0] for c in repo.record.call_args_list}
    agent_ev = records["agent"]
    assert agent_ev.name == "orchestrator"
    assert agent_ev.success is True
    assert agent_ev.user_id == "u1"
    assert agent_ev.session_id == "s1"

    model_ev = records["model"]
    assert model_ev.name == "gemini-2.5-flash"
    assert model_ev.tokens_in == 100
    assert model_ev.tokens_out == 25
    assert model_ev.caller == "orchestrator"
    assert model_ev.metadata.get("token_source") == "adk_usage_metadata"

    tool_ev = records["tool"]
    assert tool_ev.name == "create_board_task"
    assert tool_ev.caller == "orchestrator"


@pytest.mark.asyncio
async def test_runner_records_failure_on_exception():
    agent = MagicMock()
    agent.name = "orchestrator"
    session_service = AsyncMock()
    repo = MagicMock()
    recorder = UsageRecorder(repo=repo, enabled=True)

    async def fake_run(**kwargs):
        yield _event(text="partial")
        raise RuntimeError("stream aborted")

    with patch("gclaw.dispatch.runner.Runner") as MockRunner:
        MockRunner.return_value.run_async = fake_run
        runner = AgentRunner(
            agent=agent,
            app_name="gclaw",
            session_service=session_service,
            usage_recorder=recorder,
        )
        with pytest.raises(RuntimeError):
            await runner.run(user_id="u1", session_id="s1", message="hi")

    agent_evs = [c.args[0] for c in repo.record.call_args_list
                 if c.args[0].kind.value == "agent"]
    assert len(agent_evs) == 1
    assert agent_evs[0].success is False
    assert "stream aborted" in (agent_evs[0].error or "")


@pytest.mark.asyncio
async def test_runner_without_recorder_is_silent():
    agent = MagicMock()
    agent.name = "orchestrator"
    session_service = AsyncMock()

    async def fake_run(**kwargs):
        yield _event(text="hi", final=True)

    with patch("gclaw.dispatch.runner.Runner") as MockRunner:
        MockRunner.return_value.run_async = fake_run
        runner = AgentRunner(
            agent=agent,
            app_name="gclaw",
            session_service=session_service,
        )
        resp = await runner.run(user_id="u1", session_id="s1", message="hi")
    assert resp.text == "hi"
