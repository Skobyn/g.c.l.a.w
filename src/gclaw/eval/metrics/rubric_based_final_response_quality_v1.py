"""Free-form rubric-based response quality (judge as scorer)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from gclaw.eval.evalset import (
    EvalCase,
    EvalCaseResult,
    MetricScore,
    RubricBased,
)

if TYPE_CHECKING:
    from gclaw.eval.judge import JudgeClient


METRIC_NAME = "rubric_based_final_response_quality_v1"

PROMPT_TEMPLATE = """\
You are scoring an agent's response against a free-form rubric.

User input:
{input}

Agent response:
{response}

Rubric (scoring criteria):
{rubric}

Apply the rubric strictly. Reply with a single JSON object: \
{{"score": <0..1 float>, "rationale": "<short reason citing the rubric>"}}.
"""


async def rubric_based_final_response_quality_v1_score(
    case: EvalCase,
    result: EvalCaseResult,
    judge: "JudgeClient | None" = None,
) -> MetricScore | None:
    expected = case.expected_response
    if not isinstance(expected, RubricBased):
        return None
    if judge is None:
        return MetricScore(
            metric=METRIC_NAME,
            score=0.0,
            rationale="judge client unavailable; skipping rubric scoring",
        )

    prompt = PROMPT_TEMPLATE.format(
        input=case.input,
        response=result.response_text or "(no response)",
        rubric=expected.rubric,
    )
    verdict = await judge.ask(
        input_=case.input,
        response=result.response_text or "",
        rubric=f"{METRIC_NAME}::{expected.rubric}",
        prompt=prompt,
    )
    return MetricScore(
        metric=METRIC_NAME,
        score=verdict.score,
        rationale=verdict.rationale,
    )
