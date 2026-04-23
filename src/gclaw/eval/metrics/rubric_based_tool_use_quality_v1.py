"""Free-form rubric-based tool-use review (judge inspects trajectory)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from gclaw.eval.evalset import (
    EvalCase,
    EvalCaseResult,
    MetricScore,
    RubricBasedToolUse,
)

if TYPE_CHECKING:
    from gclaw.eval.judge import JudgeClient


METRIC_NAME = "rubric_based_tool_use_quality_v1"

PROMPT_TEMPLATE = """\
You are reviewing an agent's tool-use trajectory against a rubric.

User input:
{input}

Tool calls the agent made (ordered list):
{trajectory}

Rubric (scoring criteria for tool-use quality):
{rubric}

Score how well the trajectory satisfies the rubric. Penalise unnecessary \
calls, wrong tools, missing required steps. Reward correct tool choice and \
sensible argument shape. Reply with a single JSON object: \
{{"score": <0..1 float>, "rationale": "<short reason>"}}.
"""


def _format_trajectory(tool_calls: list[dict]) -> str:
    if not tool_calls:
        return "(no tool calls)"
    lines: list[str] = []
    for i, call in enumerate(tool_calls, 1):
        name = call.get("name", "?")
        args = call.get("args") or {}
        try:
            args_str = json.dumps(args, sort_keys=True)
        except TypeError:
            args_str = str(args)
        lines.append(f"{i}. {name}({args_str})")
    return "\n".join(lines)


async def rubric_based_tool_use_quality_v1_score(
    case: EvalCase,
    result: EvalCaseResult,
    judge: "JudgeClient | None" = None,
) -> MetricScore | None:
    expected = case.expected_response
    if not isinstance(expected, RubricBasedToolUse):
        return None
    if judge is None:
        return MetricScore(
            metric=METRIC_NAME,
            score=0.0,
            rationale="judge client unavailable; skipping tool-use rubric",
        )

    trajectory_str = _format_trajectory(result.tool_calls)
    prompt = PROMPT_TEMPLATE.format(
        input=case.input,
        trajectory=trajectory_str,
        rubric=expected.rubric,
    )
    verdict = await judge.ask(
        input_=case.input,
        response=trajectory_str,
        rubric=f"{METRIC_NAME}::{expected.rubric}",
        prompt=prompt,
    )
    return MetricScore(
        metric=METRIC_NAME,
        score=verdict.score,
        rationale=verdict.rationale,
    )
