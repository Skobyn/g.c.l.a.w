"""Semantic response match — judge says "is B a valid answer to A?"."""

from __future__ import annotations

from typing import TYPE_CHECKING

from gclaw.eval.evalset import (
    EvalCase,
    EvalCaseResult,
    FinalResponseMatchV2,
    MetricScore,
)

if TYPE_CHECKING:
    from gclaw.eval.judge import JudgeClient


METRIC_NAME = "final_response_match_v2"

PROMPT_TEMPLATE = """\
You are scoring whether a candidate response is a semantically valid \
answer to a user input.

User input:
{input}

Expected answer (reference; the candidate need not be word-identical):
{expected}

Candidate response:
{response}

{rubric_block}\
Score 1.0 if the candidate conveys the same answer as the reference \
(synonyms, rewording, extra detail are all fine). Score 0.0 if it \
contradicts the reference, omits the key fact, or refuses. Partial \
credit (0.3 / 0.5 / 0.7) for partially correct answers.

Reply with a single JSON object: {{"score": <0..1 float>, \
"rationale": "<short reason>"}}.
"""


async def final_response_match_v2_score(
    case: EvalCase,
    result: EvalCaseResult,
    judge: "JudgeClient | None" = None,
) -> MetricScore | None:
    expected = case.expected_response
    if not isinstance(expected, FinalResponseMatchV2):
        return None
    if judge is None:
        return MetricScore(
            metric=METRIC_NAME,
            score=0.0,
            rationale="judge client unavailable; skipping semantic check",
        )

    rubric_block = ""
    if expected.rubric:
        rubric_block = f"Additional rubric:\n{expected.rubric}\n\n"

    prompt = PROMPT_TEMPLATE.format(
        input=case.input,
        expected=expected.expected,
        response=result.response_text or "(no response)",
        rubric_block=rubric_block,
    )
    verdict = await judge.ask(
        input_=case.input,
        response=result.response_text or "",
        rubric=f"{METRIC_NAME}::{expected.expected}::{expected.rubric or ''}",
        prompt=prompt,
    )
    return MetricScore(
        metric=METRIC_NAME,
        score=verdict.score,
        rationale=verdict.rationale,
    )
