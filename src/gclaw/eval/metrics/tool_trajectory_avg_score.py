"""Tool-trajectory match metric — exact / in-order / any-order."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from gclaw.eval.evalset import EvalCase, EvalCaseResult, MetricScore

if TYPE_CHECKING:
    from gclaw.eval.judge import JudgeClient


METRIC_NAME = "tool_trajectory_avg_score"


def _args_match(
    expected: dict[str, str | None] | None, actual: dict[str, Any]
) -> bool:
    """Match each expected key against the actual args.

    A None pattern means "key must exist". Otherwise the actual value is
    coerced to str and matched as a regex (search, not full-match —
    matches the looseness of agents-cli's ``args_match``).
    """
    if not expected:
        return True
    for key, pattern in expected.items():
        if key not in actual:
            return False
        if pattern is None:
            continue
        if not re.search(pattern, str(actual[key])):
            return False
    return True


def _expected_in_order(expected) -> bool:
    """True if any expected entry sets ``order`` — switches scoring to
    in-order mode."""
    return any(e.order is not None for e in expected)


async def tool_trajectory_avg_score(
    case: EvalCase,
    result: EvalCaseResult,
    judge: "JudgeClient | None" = None,  # unused; kept for uniform sig
) -> MetricScore | None:
    """Score the trajectory.

    - No expected_tool_uses → metric does not apply, returns None.
    - All expected entries lack ``order`` → any-order scoring: score is
      ``matched / len(expected)``. Each expected entry counts at most
      once even if the agent calls the same tool multiple times.
    - At least one expected entry sets ``order`` → in-order scoring:
      walk the actual trajectory, consume expected entries in their
      ``order`` sequence, score = ``consumed / len(expected)``.
    """
    expected = case.expected_tool_uses
    if not expected:
        return None

    actual = result.tool_calls or []

    if _expected_in_order(expected):
        ordered = sorted(expected, key=lambda e: (e.order or 0))
        idx = 0
        for call in actual:
            if idx >= len(ordered):
                break
            target = ordered[idx]
            if call.get("name") == target.name and _args_match(
                target.args_match, call.get("args") or {}
            ):
                idx += 1
        score = idx / len(ordered)
        return MetricScore(
            metric=METRIC_NAME,
            score=score,
            rationale=(
                f"in-order: matched {idx}/{len(ordered)} expected tool calls"
            ),
            sub_scores={"matched": float(idx), "expected": float(len(ordered))},
            metadata={"mode": "in_order"},
        )

    # Any-order: each expected entry consumed at most once.
    used: set[int] = set()
    matched = 0
    for exp in expected:
        for i, call in enumerate(actual):
            if i in used:
                continue
            if call.get("name") == exp.name and _args_match(
                exp.args_match, call.get("args") or {}
            ):
                used.add(i)
                matched += 1
                break
    score = matched / len(expected)
    return MetricScore(
        metric=METRIC_NAME,
        score=score,
        rationale=(
            f"any-order: matched {matched}/{len(expected)} expected tool calls"
        ),
        sub_scores={"matched": float(matched), "expected": float(len(expected))},
        metadata={"mode": "any_order"},
    )
