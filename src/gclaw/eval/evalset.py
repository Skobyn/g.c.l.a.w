"""Pydantic models for the gclaw evalset format (ADR-0005).

The on-disk JSON schema is intentionally 1:1 with ``google/agents-cli``'s
evalset format so files are interchangeable: an evalset written for one
runner can be scored by the other without conversion. The runner and the
metrics live under ``gclaw.eval``; the format itself is just data.

Quick anatomy::

    {
      "name": "research-mgr",
      "description": "Routing + tool use for the Research Manager.",
      "judge_model": "gemini-2.5-flash",
      "cases": [
        {
          "case_id": "research-mgr-finds-time",
          "input": "What time is sunrise in Chicago tomorrow?",
          "agent_name": "research-mgr",
          "expected_tool_uses": [
            {"name": "web_search",
             "args_match": {"query": ".*sunrise.*chicago.*"},
             "order": 0}
          ],
          "expected_response": {
            "match_type": "rubric_based_final_response_quality_v1",
            "rubric": "The response includes a specific time and source URL."
          }
        }
      ]
    }

The ``expected_response`` block discriminates on ``match_type``; each
variant carries its own fields. Loaders use the discriminator to
hydrate the right subclass.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


# ── Tool-use expectations ─────────────────────────────────────────────────


class ToolUseExpectation(BaseModel):
    """One expected tool call for a case.

    ``args_match`` maps argument name → regex pattern. A None pattern
    means "argument must be present, value not checked"; a missing key
    means "we don't care about that argument". ``order`` is optional —
    when set, the trajectory metric can score in-order vs any-order.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    args_match: dict[str, str | None] | None = None
    order: int | None = None


# ── Expected-response variants ────────────────────────────────────────────


class ResponseMatch(BaseModel):
    """Lexical comparison: substring or fuzzy ratio."""

    model_config = ConfigDict(extra="forbid")

    match_type: Literal["response_match_score"] = "response_match_score"
    expected: str
    threshold: float = 0.7  # used by fuzzy mode; ignored for substring
    mode: Literal["substring", "fuzzy"] = "substring"
    case_sensitive: bool = False


class FinalResponseMatchV2(BaseModel):
    """Semantic check via the judge model: "is B a valid answer to A?"."""

    model_config = ConfigDict(extra="forbid")

    match_type: Literal["final_response_match_v2"] = "final_response_match_v2"
    expected: str
    rubric: str | None = None  # extra criteria fed to the judge


class RubricBased(BaseModel):
    """Free-form judge rubric → 0..1 quality score."""

    model_config = ConfigDict(extra="forbid")

    match_type: Literal[
        "rubric_based_final_response_quality_v1"
    ] = "rubric_based_final_response_quality_v1"
    rubric: str


class RubricBasedToolUse(BaseModel):
    """Judge reviews the trajectory against a rubric."""

    model_config = ConfigDict(extra="forbid")

    match_type: Literal[
        "rubric_based_tool_use_quality_v1"
    ] = "rubric_based_tool_use_quality_v1"
    rubric: str


class HallucinationsCheck(BaseModel):
    """Judge fact-checks the response against captured tool outputs."""

    model_config = ConfigDict(extra="forbid")

    match_type: Literal["hallucinations_v1"] = "hallucinations_v1"
    rubric: str | None = None


class SafetyCheck(BaseModel):
    """Judge decides whether the response refused appropriately."""

    model_config = ConfigDict(extra="forbid")

    match_type: Literal["safety_v1"] = "safety_v1"
    rubric: str | None = None
    must_refuse: bool = True


ExpectedResponse = Annotated[
    Union[
        ResponseMatch,
        FinalResponseMatchV2,
        RubricBased,
        RubricBasedToolUse,
        HallucinationsCheck,
        SafetyCheck,
    ],
    Field(discriminator="match_type"),
]


# ── Cases + evalset ───────────────────────────────────────────────────────


class EvalCase(BaseModel):
    """One eval case: input + agent + expected trajectory + expected response."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    input: str
    agent_name: str
    expected_tool_uses: list[ToolUseExpectation] = Field(default_factory=list)
    expected_response: ExpectedResponse | None = None
    user_id: str = "eval_user"
    metadata: dict[str, Any] = Field(default_factory=dict)


class Evalset(BaseModel):
    """Top-level evalset document — name + cases + judge defaults."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    judge_model: str = "gemini-2.5-flash"
    cases: list[EvalCase] = Field(default_factory=list)

    # ── I/O ────────────────────────────────────────────────────────────

    @classmethod
    def from_json(cls, path: str | Path) -> "Evalset":
        with open(path) as f:
            data = json.load(f)
        return cls.model_validate(data)

    def to_json(self, path: str | Path, *, indent: int = 2) -> None:
        with open(path, "w") as f:
            json.dump(
                self.model_dump(mode="json", exclude_none=True),
                f,
                indent=indent,
            )
            f.write("\n")


# ── Result models ─────────────────────────────────────────────────────────


class MetricScore(BaseModel):
    """One metric's verdict on one case."""

    model_config = ConfigDict(extra="forbid")

    metric: str
    score: float
    rationale: str | None = None
    sub_scores: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvalCaseResult(BaseModel):
    """Output of running a single case through the EvalRunner."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    agent_name: str
    input: str
    response_text: str = ""
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    metrics: list[MetricScore] = Field(default_factory=list)
    duration_ms: int = 0

    @property
    def metric_map(self) -> dict[str, float]:
        """Quick name→score lookup for compare/report code."""
        return {m.metric: m.score for m in self.metrics}


class EvalRunResult(BaseModel):
    """Full result of an evalset run."""

    model_config = ConfigDict(extra="forbid")

    evalset_name: str
    started_at: str  # ISO-8601
    finished_at: str
    judge_model: str
    cases: list[EvalCaseResult] = Field(default_factory=list)
    metric_averages: dict[str, float] = Field(default_factory=dict)

    @classmethod
    def from_json(cls, path: str | Path) -> "EvalRunResult":
        with open(path) as f:
            data = json.load(f)
        return cls.model_validate(data)

    def to_json(self, path: str | Path, *, indent: int = 2) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(
                self.model_dump(mode="json", exclude_none=True),
                f,
                indent=indent,
            )
            f.write("\n")
