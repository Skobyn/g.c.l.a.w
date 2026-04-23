"""Tests for the ADR-0005 metric set (no live LLM calls)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from gclaw.eval.evalset import (
    EvalCase,
    EvalCaseResult,
    FinalResponseMatchV2,
    HallucinationsCheck,
    ResponseMatch,
    RubricBased,
    RubricBasedToolUse,
    SafetyCheck,
    ToolUseExpectation,
)
from gclaw.eval.judge import JudgeClient, JudgeVerdict
from gclaw.eval.metrics import (
    final_response_match_v2_score,
    hallucinations_v1_score,
    response_match_score,
    rubric_based_final_response_quality_v1_score,
    rubric_based_tool_use_quality_v1_score,
    safety_v1_score,
    tool_trajectory_avg_score,
)


def _case(
    tool_uses=(),
    expected_response=None,
    case_id="c1",
    agent_name="research-mgr",
    user_input="hi",
):
    return EvalCase(
        case_id=case_id,
        input=user_input,
        agent_name=agent_name,
        expected_tool_uses=list(tool_uses),
        expected_response=expected_response,
    )


def _result(tool_calls=(), response_text=""):
    return EvalCaseResult(
        case_id="c1",
        agent_name="research-mgr",
        input="hi",
        response_text=response_text,
        tool_calls=list(tool_calls),
    )


# ── tool_trajectory_avg_score ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tool_trajectory_metric_exact_match():
    case = _case(
        tool_uses=[
            ToolUseExpectation(
                name="web_search", args_match={"query": ".*chicago.*"}
            )
        ]
    )
    result = _result(
        tool_calls=[{"name": "web_search", "args": {"query": "chicago weather"}}]
    )
    score = await tool_trajectory_avg_score(case, result, judge=None)
    assert score is not None
    assert score.score == 1.0


@pytest.mark.asyncio
async def test_tool_trajectory_metric_partial_match():
    """Two of three expected calls present → ~0.66."""
    case = _case(
        tool_uses=[
            ToolUseExpectation(name="a"),
            ToolUseExpectation(name="b"),
            ToolUseExpectation(name="c"),
        ]
    )
    result = _result(
        tool_calls=[{"name": "a", "args": {}}, {"name": "b", "args": {}}]
    )
    score = await tool_trajectory_avg_score(case, result, judge=None)
    assert score is not None
    assert score.score == pytest.approx(2 / 3, abs=0.01)


@pytest.mark.asyncio
async def test_tool_trajectory_metric_in_order_pass():
    case = _case(
        tool_uses=[
            ToolUseExpectation(name="a", order=0),
            ToolUseExpectation(name="b", order=1),
        ]
    )
    result = _result(
        tool_calls=[
            {"name": "a", "args": {}},
            {"name": "b", "args": {}},
        ]
    )
    score = await tool_trajectory_avg_score(case, result, judge=None)
    assert score is not None
    assert score.score == 1.0
    assert score.metadata["mode"] == "in_order"


@pytest.mark.asyncio
async def test_tool_trajectory_metric_in_order_fail():
    """Calls in the wrong order — second expected never gets consumed."""
    case = _case(
        tool_uses=[
            ToolUseExpectation(name="a", order=0),
            ToolUseExpectation(name="b", order=1),
        ]
    )
    # b first, then a — the in-order walker consumes a (it's still
    # waiting for ``a`` first), then runs out of expectations.
    result = _result(
        tool_calls=[
            {"name": "b", "args": {}},
            {"name": "a", "args": {}},
        ]
    )
    score = await tool_trajectory_avg_score(case, result, judge=None)
    assert score is not None
    # We matched a (1 of 2); b never came after a.
    assert score.score == 0.5


@pytest.mark.asyncio
async def test_tool_trajectory_metric_skips_when_no_expectations():
    case = _case(tool_uses=())
    result = _result(tool_calls=[{"name": "a", "args": {}}])
    score = await tool_trajectory_avg_score(case, result, judge=None)
    assert score is None


@pytest.mark.asyncio
async def test_tool_trajectory_args_pattern_required():
    """An expected pattern that doesn't match → that expectation isn't satisfied."""
    case = _case(
        tool_uses=[
            ToolUseExpectation(
                name="web_search", args_match={"query": ".*chicago.*"}
            )
        ]
    )
    result = _result(
        tool_calls=[{"name": "web_search", "args": {"query": "phoenix weather"}}]
    )
    score = await tool_trajectory_avg_score(case, result, judge=None)
    assert score is not None
    assert score.score == 0.0


# ── response_match_score ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_response_match_score_substring():
    case = _case(
        expected_response=ResponseMatch(expected="hello", mode="substring")
    )
    result = _result(response_text="HELLO world")
    score = await response_match_score(case, result, judge=None)
    assert score is not None
    assert score.score == 1.0
    # Negative case
    result_neg = _result(response_text="goodbye world")
    neg = await response_match_score(case, result_neg, judge=None)
    assert neg is not None
    assert neg.score == 0.0


@pytest.mark.asyncio
async def test_response_match_score_threshold_fuzzy():
    case = _case(
        expected_response=ResponseMatch(
            expected="the quick brown fox",
            mode="fuzzy",
            threshold=0.8,
        )
    )
    near = _result(response_text="the quick brown fox jumps")
    score = await response_match_score(case, near, judge=None)
    assert score is not None
    assert score.score >= 0.8
    assert score.metadata["passed"] is True

    far = _result(response_text="completely unrelated text")
    score_far = await response_match_score(case, far, judge=None)
    assert score_far is not None
    assert score_far.score < 0.5
    assert score_far.metadata["passed"] is False


# ── final_response_match_v2 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_final_response_match_v2_uses_judge():
    """The metric must hand the judge a prompt containing input / expected /
    response / rubric, and use the parsed score."""
    captured: dict[str, str] = {}

    async def fake_ask(prompt: str) -> str:
        captured["prompt"] = prompt
        return '{"score": 0.85, "rationale": "close enough"}'

    judge = JudgeClient(ask_fn=fake_ask)

    case = _case(
        user_input="What's 2+2?",
        expected_response=FinalResponseMatchV2(
            expected="four", rubric="Numbers in words OK."
        ),
    )
    result = _result(response_text="It's 4.")
    score = await final_response_match_v2_score(case, result, judge=judge)
    assert score is not None
    assert score.score == pytest.approx(0.85)
    assert "What's 2+2?" in captured["prompt"]
    assert "four" in captured["prompt"]
    assert "It's 4." in captured["prompt"]
    assert "Numbers in words OK." in captured["prompt"]


@pytest.mark.asyncio
async def test_rubric_based_final_response_quality_uses_judge():
    async def fake_ask(prompt: str) -> str:
        assert "rubric goes here" in prompt
        return '{"score": 0.6}'

    judge = JudgeClient(ask_fn=fake_ask)
    case = _case(
        expected_response=RubricBased(rubric="rubric goes here"),
    )
    result = _result(response_text="meh")
    score = await rubric_based_final_response_quality_v1_score(
        case, result, judge=judge
    )
    assert score is not None
    assert score.score == pytest.approx(0.6)


@pytest.mark.asyncio
async def test_rubric_based_tool_use_quality_includes_trajectory():
    captured: dict[str, str] = {}

    async def fake_ask(prompt: str) -> str:
        captured["prompt"] = prompt
        return '{"score": 0.9, "rationale": "ok"}'

    judge = JudgeClient(ask_fn=fake_ask)
    case = _case(
        expected_response=RubricBasedToolUse(rubric="Use web_search first."),
    )
    result = _result(
        tool_calls=[{"name": "web_search", "args": {"q": "x"}}]
    )
    score = await rubric_based_tool_use_quality_v1_score(
        case, result, judge=judge
    )
    assert score is not None
    assert score.score == 0.9
    assert "web_search" in captured["prompt"]


@pytest.mark.asyncio
async def test_hallucinations_metric_passes_tool_outputs_to_judge():
    captured: dict[str, str] = {}

    async def fake_ask(prompt: str) -> str:
        captured["prompt"] = prompt
        return '{"score": 0.0, "rationale": "fabricated URL"}'

    judge = JudgeClient(ask_fn=fake_ask)
    case = _case(expected_response=HallucinationsCheck())
    result = _result(
        response_text="See https://example.com/fake",
        tool_calls=[{"name": "web_search", "args": {"q": "x"}}],
    )
    score = await hallucinations_v1_score(case, result, judge=judge)
    assert score is not None
    assert score.score == 0.0
    assert "web_search" in captured["prompt"]
    assert "fake" in captured["prompt"]


@pytest.mark.asyncio
async def test_safety_metric_signals_must_refuse_in_prompt():
    captured: dict[str, str] = {}

    async def fake_ask(prompt: str) -> str:
        captured["prompt"] = prompt
        return '{"score": 1.0, "rationale": "refused cleanly"}'

    judge = JudgeClient(ask_fn=fake_ask)
    case = _case(expected_response=SafetyCheck(must_refuse=True))
    result = _result(response_text="I can't help with that.")
    score = await safety_v1_score(case, result, judge=judge)
    assert score is not None
    assert score.score == 1.0
    assert "refuse" in captured["prompt"].lower()


# ── metrics opt-out cleanly when not applicable ──────────────────────────


@pytest.mark.asyncio
async def test_metrics_return_none_when_expected_response_mismatched():
    """A response_match_score metric should not score a rubric-based case."""
    case = _case(
        expected_response=RubricBased(rubric="x")
    )
    result = _result(response_text="y")
    assert await response_match_score(case, result, judge=None) is None
    assert (
        await final_response_match_v2_score(case, result, judge=None) is None
    )
    assert await safety_v1_score(case, result, judge=None) is None
    assert await hallucinations_v1_score(case, result, judge=None) is None


@pytest.mark.asyncio
async def test_judge_metrics_no_op_when_judge_is_none():
    """Rubric metrics produce a 0.0 placeholder rather than crash without a judge."""
    case = _case(expected_response=RubricBased(rubric="x"))
    result = _result(response_text="y")
    score = await rubric_based_final_response_quality_v1_score(
        case, result, judge=None
    )
    assert score is not None
    assert score.score == 0.0
    assert "judge" in (score.rationale or "").lower()
