"""Metric implementations for the gclaw evalset framework.

Every metric exposes ``score(case, result, judge) -> MetricScore``. The
metric is responsible for deciding whether it applies (e.g. response
metrics no-op for cases without ``expected_response``) and for picking a
default 0..1 score when the case carries no expectation it can act on.
"""

from __future__ import annotations

from gclaw.eval.metrics.final_response_match_v2 import (
    final_response_match_v2_score,
)
from gclaw.eval.metrics.hallucinations_v1 import hallucinations_v1_score
from gclaw.eval.metrics.response_match_score import response_match_score
from gclaw.eval.metrics.rubric_based_final_response_quality_v1 import (
    rubric_based_final_response_quality_v1_score,
)
from gclaw.eval.metrics.rubric_based_tool_use_quality_v1 import (
    rubric_based_tool_use_quality_v1_score,
)
from gclaw.eval.metrics.safety_v1 import safety_v1_score
from gclaw.eval.metrics.tool_trajectory_avg_score import (
    tool_trajectory_avg_score,
)

# Registry: metric name → callable. The runner walks this map per case
# and asks each entry whether it applies. New metrics drop in by adding
# to the dict.
METRICS = {
    "tool_trajectory_avg_score": tool_trajectory_avg_score,
    "response_match_score": response_match_score,
    "final_response_match_v2": final_response_match_v2_score,
    "rubric_based_final_response_quality_v1": (
        rubric_based_final_response_quality_v1_score
    ),
    "rubric_based_tool_use_quality_v1": (
        rubric_based_tool_use_quality_v1_score
    ),
    "hallucinations_v1": hallucinations_v1_score,
    "safety_v1": safety_v1_score,
}

__all__ = [
    "METRICS",
    "tool_trajectory_avg_score",
    "response_match_score",
    "final_response_match_v2_score",
    "rubric_based_final_response_quality_v1_score",
    "rubric_based_tool_use_quality_v1_score",
    "hallucinations_v1_score",
    "safety_v1_score",
]
