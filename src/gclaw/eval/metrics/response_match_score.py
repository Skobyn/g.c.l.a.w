"""Lexical response match — substring or fuzzy ratio."""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import TYPE_CHECKING

from gclaw.eval.evalset import EvalCase, EvalCaseResult, MetricScore, ResponseMatch

if TYPE_CHECKING:
    from gclaw.eval.judge import JudgeClient


METRIC_NAME = "response_match_score"


async def response_match_score(
    case: EvalCase,
    result: EvalCaseResult,
    judge: "JudgeClient | None" = None,  # unused
) -> MetricScore | None:
    """Score the response lexically.

    Substring mode: 1.0 if ``expected`` is contained in the actual
    response (case sensitivity per the spec), else 0.0.

    Fuzzy mode: SequenceMatcher ratio; passes when ratio >= threshold.
    The score is the ratio itself (so a near-miss shows up as 0.83
    rather than collapsing to 0.0).
    """
    expected = case.expected_response
    if not isinstance(expected, ResponseMatch):
        return None

    actual = result.response_text or ""
    target = expected.expected
    if not expected.case_sensitive:
        actual_cmp = actual.lower()
        target_cmp = target.lower()
    else:
        actual_cmp = actual
        target_cmp = target

    if expected.mode == "substring":
        ok = target_cmp in actual_cmp
        return MetricScore(
            metric=METRIC_NAME,
            score=1.0 if ok else 0.0,
            rationale=(
                f"substring {'found' if ok else 'missing'}: {target!r}"
            ),
            metadata={"mode": "substring"},
        )

    ratio = SequenceMatcher(None, actual_cmp, target_cmp).ratio()
    return MetricScore(
        metric=METRIC_NAME,
        score=float(ratio),
        rationale=(
            f"fuzzy ratio={ratio:.3f} threshold={expected.threshold:.2f}"
        ),
        sub_scores={"ratio": float(ratio), "threshold": expected.threshold},
        metadata={"mode": "fuzzy", "passed": ratio >= expected.threshold},
    )
