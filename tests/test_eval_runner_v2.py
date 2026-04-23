"""Tests for the ADR-0005 EvalRunner."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from gclaw.dispatch.runner import AgentResponse
from gclaw.eval.evalset import (
    EvalCase,
    Evalset,
    ResponseMatch,
    RubricBased,
    ToolUseExpectation,
)
from gclaw.eval.evalset_runner import EvalRunner
from gclaw.eval.judge import JudgeClient


def _stub_runner(tool_calls=(), text="canned response", error=None):
    runner = MagicMock()

    async def _run_trace(*, user_id, session_id, message):
        return (
            AgentResponse(
                text=text,
                tool_calls=list(tool_calls),
                is_final=True,
            ),
            error,
        )

    runner.run_trace = AsyncMock(side_effect=_run_trace)
    return runner


@pytest.mark.asyncio
async def test_runner_executes_case_and_scores():
    """A case with a trajectory expectation + lexical response check should
    produce two MetricScores (trajectory + response_match_score)."""
    case = EvalCase(
        case_id="c1",
        input="say hi",
        agent_name="research-mgr",
        expected_tool_uses=[
            ToolUseExpectation(name="web_search")
        ],
        expected_response=ResponseMatch(
            expected="hi", mode="substring"
        ),
    )
    evalset = Evalset(name="demo", cases=[case])
    stub = _stub_runner(
        tool_calls=[{"name": "web_search", "args": {"q": "hi"}}],
        text="hi there",
    )
    runner = EvalRunner(runner_builder=lambda c: stub)
    result = await runner.run_evalset(evalset)

    assert len(result.cases) == 1
    cr = result.cases[0]
    assert cr.case_id == "c1"
    assert cr.response_text == "hi there"
    assert cr.tool_calls == [{"name": "web_search", "args": {"q": "hi"}}]
    metric_map = cr.metric_map
    assert metric_map["tool_trajectory_avg_score"] == 1.0
    assert metric_map["response_match_score"] == 1.0
    assert "tool_trajectory_avg_score" in result.metric_averages
    assert result.metric_averages["response_match_score"] == 1.0


@pytest.mark.asyncio
async def test_runner_uses_judge_for_rubric_metric():
    case = EvalCase(
        case_id="c2",
        input="explain entropy",
        agent_name="research-mgr",
        expected_response=RubricBased(
            rubric="Mentions disorder or randomness."
        ),
    )
    evalset = Evalset(name="rubric-demo", cases=[case])

    async def fake_ask(prompt: str) -> str:
        return '{"score": 0.8, "rationale": "covers the concept"}'

    judge = JudgeClient(ask_fn=fake_ask)
    stub = _stub_runner(
        text="Entropy measures disorder in a system."
    )
    runner = EvalRunner(runner_builder=lambda c: stub, judge=judge)
    result = await runner.run_evalset(evalset)

    metric_map = result.cases[0].metric_map
    assert metric_map["rubric_based_final_response_quality_v1"] == 0.8


@pytest.mark.asyncio
async def test_runner_writes_result_file(tmp_path):
    case = EvalCase(
        case_id="c1",
        input="hi",
        agent_name="research-mgr",
        expected_tool_uses=[ToolUseExpectation(name="web_search")],
    )
    evalset = Evalset(name="ws-demo", cases=[case])
    stub = _stub_runner(
        tool_calls=[{"name": "web_search", "args": {}}], text="ok"
    )
    runner = EvalRunner(runner_builder=lambda c: stub)
    result, out_path = await runner.run_and_save(
        evalset, results_dir=tmp_path
    )

    assert out_path.exists()
    payload = json.loads(out_path.read_text())
    assert payload["evalset_name"] == "ws-demo"
    assert payload["cases"][0]["case_id"] == "c1"
    # Round-trip through the model — schema must validate.
    from gclaw.eval.evalset import EvalRunResult
    reloaded = EvalRunResult.from_json(out_path)
    assert reloaded == result


@pytest.mark.asyncio
async def test_runner_captures_partial_trajectory_on_tool_error():
    """``run_trace`` returning an error must not erase the captured tool call."""
    case = EvalCase(
        case_id="c1",
        input="mark t7 done",
        agent_name="orchestrator",
        expected_tool_uses=[ToolUseExpectation(name="complete_board_task")],
    )
    evalset = Evalset(name="err-demo", cases=[case])
    stub = _stub_runner(
        tool_calls=[
            {"name": "complete_board_task", "args": {"task_id": "t7"}}
        ],
        text="",
        error="ValueError: Task t7 not found",
    )
    runner = EvalRunner(runner_builder=lambda c: stub)
    result = await runner.run_evalset(evalset)
    cr = result.cases[0]
    assert cr.error is not None
    assert "t7" in cr.error
    assert cr.metric_map["tool_trajectory_avg_score"] == 1.0


@pytest.mark.asyncio
async def test_runner_metric_averages_only_over_applicable_cases():
    """A metric that only fires on one case shouldn't drag averages down
    on cases where it wasn't applicable."""
    cases = [
        EvalCase(
            case_id="a",
            input="i1",
            agent_name="x",
            expected_tool_uses=[ToolUseExpectation(name="t")],
        ),
        EvalCase(
            case_id="b",
            input="i2",
            agent_name="x",
            expected_response=ResponseMatch(expected="hi", mode="substring"),
        ),
    ]
    evalset = Evalset(name="mixed", cases=cases)
    stub_a = _stub_runner(
        tool_calls=[{"name": "t", "args": {}}], text="ok"
    )
    stub_b = _stub_runner(text="hi there")
    runners = {"a": stub_a, "b": stub_b}
    runner = EvalRunner(runner_builder=lambda c: runners[c.case_id])
    result = await runner.run_evalset(evalset)
    # Trajectory metric only applied to case a.
    assert result.metric_averages["tool_trajectory_avg_score"] == 1.0
    # Response metric only applied to case b.
    assert result.metric_averages["response_match_score"] == 1.0


def test_runner_requires_factory_or_builder():
    with pytest.raises(ValueError):
        EvalRunner()
