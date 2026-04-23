"""Schema round-trip tests for the ADR-0005 evalset format."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gclaw.eval.evalset import (
    EvalCase,
    EvalCaseResult,
    EvalRunResult,
    Evalset,
    FinalResponseMatchV2,
    HallucinationsCheck,
    MetricScore,
    ResponseMatch,
    RubricBased,
    RubricBasedToolUse,
    SafetyCheck,
    ToolUseExpectation,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_EVALSET = REPO_ROOT / "tests" / "eval" / "evalsets" / "research-mgr.json"


def test_evalset_load_dump_roundtrip(tmp_path):
    """Load the sample evalset, dump it, reload — must equal the original."""
    original = Evalset.from_json(SAMPLE_EVALSET)
    out = tmp_path / "round.json"
    original.to_json(out)
    reloaded = Evalset.from_json(out)
    assert reloaded == original
    # And the dumped JSON should still be valid against the same schema.
    reparsed = Evalset.model_validate(json.loads(out.read_text()))
    assert reparsed == original


def test_evalset_discriminated_union_picks_right_subclass():
    """The discriminator on ``match_type`` must hydrate the right class."""
    payload = {
        "name": "demo",
        "cases": [
            {
                "case_id": "a",
                "input": "x",
                "agent_name": "research-mgr",
                "expected_response": {
                    "match_type": "response_match_score",
                    "expected": "hello",
                },
            },
            {
                "case_id": "b",
                "input": "y",
                "agent_name": "research-mgr",
                "expected_response": {
                    "match_type": "rubric_based_final_response_quality_v1",
                    "rubric": "Good answer.",
                },
            },
            {
                "case_id": "c",
                "input": "z",
                "agent_name": "research-mgr",
                "expected_response": {
                    "match_type": "final_response_match_v2",
                    "expected": "the moon",
                },
            },
            {
                "case_id": "d",
                "input": "w",
                "agent_name": "research-mgr",
                "expected_response": {
                    "match_type": "hallucinations_v1",
                },
            },
            {
                "case_id": "e",
                "input": "v",
                "agent_name": "research-mgr",
                "expected_response": {
                    "match_type": "safety_v1",
                    "must_refuse": True,
                },
            },
            {
                "case_id": "f",
                "input": "u",
                "agent_name": "research-mgr",
                "expected_response": {
                    "match_type": "rubric_based_tool_use_quality_v1",
                    "rubric": "Tool choice is sensible.",
                },
            },
        ],
    }
    es = Evalset.model_validate(payload)
    assert isinstance(es.cases[0].expected_response, ResponseMatch)
    assert isinstance(es.cases[1].expected_response, RubricBased)
    assert isinstance(es.cases[2].expected_response, FinalResponseMatchV2)
    assert isinstance(es.cases[3].expected_response, HallucinationsCheck)
    assert isinstance(es.cases[4].expected_response, SafetyCheck)
    assert isinstance(es.cases[5].expected_response, RubricBasedToolUse)


def test_tool_use_expectation_keeps_args_match_and_order():
    expectation = ToolUseExpectation(
        name="web_search",
        args_match={"query": ".*chicago.*", "lang": None},
        order=1,
    )
    dumped = expectation.model_dump()
    restored = ToolUseExpectation.model_validate(dumped)
    assert restored == expectation


def test_evalset_extra_fields_rejected():
    """``extra='forbid'`` must reject unknown top-level keys."""
    with pytest.raises(Exception):  # pydantic ValidationError
        Evalset.model_validate({"name": "x", "totally_made_up": True})


def test_eval_run_result_to_from_json(tmp_path):
    """``EvalRunResult`` round-trips through JSON."""
    res = EvalRunResult(
        evalset_name="demo",
        started_at="2026-04-22T22:00:00+00:00",
        finished_at="2026-04-22T22:01:00+00:00",
        judge_model="gemini-2.5-flash",
        cases=[
            EvalCaseResult(
                case_id="a",
                agent_name="research-mgr",
                input="hi",
                response_text="hello",
                tool_calls=[{"name": "web_search", "args": {"q": "hi"}}],
                metrics=[
                    MetricScore(metric="response_match_score", score=1.0)
                ],
            )
        ],
        metric_averages={"response_match_score": 1.0},
    )
    out = tmp_path / "run.json"
    res.to_json(out)
    reloaded = EvalRunResult.from_json(out)
    assert reloaded == res


def test_eval_case_metric_map_returns_per_metric_scores():
    cr = EvalCaseResult(
        case_id="x",
        agent_name="a",
        input="i",
        metrics=[
            MetricScore(metric="m1", score=0.5),
            MetricScore(metric="m2", score=0.9),
        ],
    )
    assert cr.metric_map == {"m1": 0.5, "m2": 0.9}
