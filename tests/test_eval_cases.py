"""Unit tests for the eval harness.

These tests exercise `run_eval` against a mocked AgentRunner so they
don't hit live Gemini. The full golden-case run against the real
orchestrator goes through `python -m gclaw.eval` and is run manually
(it costs real tokens).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from gclaw.dispatch.runner import AgentResponse
from gclaw.eval.cases import GOLDEN_CASES, EvalCase
from gclaw.eval.runner import EvalResult, run_eval


def _make_runner_that_returns(tool_calls_per_query: dict[str, list[str]]):
    """Build a MagicMock AgentRunner whose run() method returns an
    AgentResponse with tool_calls that depend on the incoming message."""
    runner = MagicMock()

    async def _run(*, user_id, session_id, message):
        tool_names = tool_calls_per_query.get(message, [])
        return AgentResponse(
            text=f"mocked response for: {message}",
            tool_calls=[{"name": n, "args": {}} for n in tool_names],
            is_final=True,
        )

    runner.run = AsyncMock(side_effect=_run)
    return runner


# ---------------------------------------------------------------------------
# Case set sanity
# ---------------------------------------------------------------------------


def test_golden_case_set_has_coverage():
    """Minimum viable coverage: at least one case per category."""
    categories = {c.category for c in GOLDEN_CASES}
    assert {"routing", "workflow", "board", "conversational"} <= categories


def test_golden_case_set_has_enough_cases():
    """Don't silently shrink the golden set. If you need to prune,
    bump this threshold consciously."""
    assert len(GOLDEN_CASES) >= 10


def test_golden_case_set_is_unique_per_query():
    """No duplicate queries — each case should exercise something distinct."""
    queries = [c.query for c in GOLDEN_CASES]
    assert len(queries) == len(set(queries))


# ---------------------------------------------------------------------------
# run_eval scoring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_eval_all_pass():
    """If every case gets the expected tool call, every case passes."""
    cases = [
        EvalCase(
            query="ask A",
            expected_tools=["tool_a"],
            description="a",
            category="routing",
        ),
        EvalCase(
            query="ask B",
            expected_tools=["tool_b"],
            description="b",
            category="routing",
        ),
    ]
    runner = _make_runner_that_returns({
        "ask A": ["tool_a"],
        "ask B": ["tool_b"],
    })

    result = await run_eval(runner, cases)

    assert result.total == 2
    assert result.passed == 2
    assert result.failed == 0
    assert result.pass_rate == 1.0


@pytest.mark.asyncio
async def test_run_eval_any_match_passes():
    """A case with multiple expected tools passes if ANY match."""
    cases = [
        EvalCase(
            query="ask",
            expected_tools=["tool_a", "tool_b"],
            description="any",
            category="routing",
        ),
    ]
    runner = _make_runner_that_returns({"ask": ["tool_b"]})

    result = await run_eval(runner, cases)

    assert result.passed == 1


@pytest.mark.asyncio
async def test_run_eval_wrong_tool_fails():
    """Getting the wrong tool counts as a failure."""
    cases = [
        EvalCase(
            query="ask",
            expected_tools=["tool_a"],
            description="wrong",
            category="routing",
        ),
    ]
    runner = _make_runner_that_returns({"ask": ["tool_c"]})

    result = await run_eval(runner, cases)

    assert result.passed == 0
    assert result.failed == 1
    assert result.cases[0].actual_tool_calls == ["tool_c"]


@pytest.mark.asyncio
async def test_run_eval_conversational_case_expects_no_tools():
    """A conversational case (empty expected_tools) passes when the
    orchestrator calls no tools, and fails when it does."""
    cases = [
        EvalCase(
            query="hi",
            expected_tools=[],
            description="small talk",
            category="conversational",
        ),
    ]

    runner_silent = _make_runner_that_returns({"hi": []})
    result_pass = await run_eval(runner_silent, cases)
    assert result_pass.passed == 1

    runner_chatty = _make_runner_that_returns({"hi": ["list_board_tasks"]})
    result_fail = await run_eval(runner_chatty, cases)
    assert result_fail.passed == 0


@pytest.mark.asyncio
async def test_run_eval_catches_exceptions_and_marks_fail():
    """A case that raises should show up as failed with an error message,
    not abort the whole run."""
    cases = [
        EvalCase(
            query="raises",
            expected_tools=["x"],
            description="error",
            category="routing",
        ),
        EvalCase(
            query="ok",
            expected_tools=["x"],
            description="ok",
            category="routing",
        ),
    ]
    runner = MagicMock()
    calls: dict[str, int] = {"n": 0}

    async def _run(*, user_id, session_id, message):
        calls["n"] += 1
        if message == "raises":
            raise RuntimeError("boom")
        return AgentResponse(
            text="ok",
            tool_calls=[{"name": "x", "args": {}}],
            is_final=True,
        )

    runner.run = AsyncMock(side_effect=_run)

    result = await run_eval(runner, cases)

    assert calls["n"] == 2  # both cases attempted
    assert result.passed == 1
    assert result.failed == 1
    assert result.cases[0].error == "boom"
    assert result.cases[1].error is None


@pytest.mark.asyncio
async def test_run_eval_defaults_to_golden_cases():
    """When cases is None, GOLDEN_CASES is used."""
    runner = MagicMock()
    runner.run = AsyncMock(
        return_value=AgentResponse(text="", tool_calls=[], is_final=True)
    )

    result = await run_eval(runner)

    assert result.total == len(GOLDEN_CASES)


def test_eval_result_summary_formats_pass_rate():
    cases = []
    r = EvalResult(cases=cases)
    assert r.summary() == "0/0 passed (0.0%)"


@pytest.mark.asyncio
async def test_run_eval_isolates_sessions_per_case():
    """Each case should run in its own session_id so state can't leak
    between cases."""
    runner = MagicMock()
    runner.run = AsyncMock(
        return_value=AgentResponse(text="", tool_calls=[], is_final=True)
    )

    cases = [
        EvalCase(query="q1", expected_tools=[], description="1", category="conversational"),
        EvalCase(query="q2", expected_tools=[], description="2", category="conversational"),
        EvalCase(query="q3", expected_tools=[], description="3", category="conversational"),
    ]
    await run_eval(runner, cases)

    session_ids = [c.kwargs["session_id"] for c in runner.run.call_args_list]
    assert session_ids == ["eval_0", "eval_1", "eval_2"]
    assert len(set(session_ids)) == 3
