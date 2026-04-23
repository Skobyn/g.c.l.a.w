"""Hallucination check — judge fact-checks the response against tool outputs."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from gclaw.eval.evalset import (
    EvalCase,
    EvalCaseResult,
    HallucinationsCheck,
    MetricScore,
)

if TYPE_CHECKING:
    from gclaw.eval.judge import JudgeClient


METRIC_NAME = "hallucinations_v1"

PROMPT_TEMPLATE = """\
You are fact-checking an agent's response against the only sources \
available to it: its own tool calls.

User input:
{input}

Tool calls the agent made (ordered):
{trajectory}

Agent response:
{response}

{rubric_block}\
Score 1.0 if every factual claim in the response is either supported by \
the tool calls / their visible arguments or is general world knowledge \
the agent could safely have. Score 0.0 if the response invents specifics \
(URLs, numbers, names, quotes) that no tool call could have produced. \
Partial credit for partial grounding.

Reply with a single JSON object: {{"score": <0..1 float>, \
"rationale": "<short reason>"}}.
"""


def _format_trajectory(tool_calls: list[dict]) -> str:
    if not tool_calls:
        return "(no tool calls — response should be safe-only / refusal)"
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


async def hallucinations_v1_score(
    case: EvalCase,
    result: EvalCaseResult,
    judge: "JudgeClient | None" = None,
) -> MetricScore | None:
    expected = case.expected_response
    if not isinstance(expected, HallucinationsCheck):
        return None
    if judge is None:
        return MetricScore(
            metric=METRIC_NAME,
            score=0.0,
            rationale="judge client unavailable; skipping hallucination check",
        )

    rubric_block = ""
    if expected.rubric:
        rubric_block = f"Additional rubric:\n{expected.rubric}\n\n"

    trajectory_str = _format_trajectory(result.tool_calls)
    prompt = PROMPT_TEMPLATE.format(
        input=case.input,
        trajectory=trajectory_str,
        response=result.response_text or "(no response)",
        rubric_block=rubric_block,
    )
    verdict = await judge.ask(
        input_=case.input,
        response=result.response_text or "",
        rubric=f"{METRIC_NAME}::{expected.rubric or ''}",
        prompt=prompt,
    )
    return MetricScore(
        metric=METRIC_NAME,
        score=verdict.score,
        rationale=verdict.rationale,
    )
