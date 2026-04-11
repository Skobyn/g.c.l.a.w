"""Score eval cases by running them through an AgentRunner.

The runner is intentionally independent of any LLM-as-judge SDK so
that a pytest-friendly subset can run against a mocked AgentRunner
without network calls. The full suite is driven by the
`python -m gclaw.eval` entrypoint against a live Gemini-backed
orchestrator.

Upgrade path: the `EvalCase` and `CaseResult` dataclasses map
cleanly onto Vertex AI Gen AI Evaluation Service `EvalDataset`
schemas. When we grow beyond name-match scoring, swap `run_eval`
for a `vertexai.evaluation.EvalTask(...)` wrapper without touching
`cases.py`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from gclaw.eval.cases import EvalCase

if TYPE_CHECKING:
    from gclaw.dispatch.runner import AgentRunner

logger = logging.getLogger(__name__)


@dataclass
class CaseResult:
    """Result of running one EvalCase through the orchestrator."""

    case: EvalCase
    passed: bool
    actual_tool_calls: list[str]
    response_text: str
    error: str | None = None

    @property
    def label(self) -> str:
        return "PASS" if self.passed else "FAIL"


@dataclass
class EvalResult:
    """Aggregate result over a whole case list."""

    cases: list[CaseResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.cases if c.passed)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def summary(self) -> str:
        """One-line summary for reports."""
        return (
            f"{self.passed}/{self.total} passed "
            f"({self.pass_rate * 100:.1f}%)"
        )


def _score_case(case: EvalCase, actual_tool_names: list[str]) -> bool:
    """Pass if any expected tool was called, or if no tool was expected
    AND none was called."""
    if not case.expected_tools:
        return len(actual_tool_names) == 0
    return any(name in actual_tool_names for name in case.expected_tools)


async def run_eval(
    agent_runner: "AgentRunner",
    cases: list[EvalCase] | None = None,
    user_id: str = "eval_user",
) -> EvalResult:
    """Run each case through the agent runner and score it.

    Each case runs in its own isolated ADK session (session_id
    `eval_{i}`) so prior turns can't leak into later cases.
    """
    from gclaw.eval.cases import GOLDEN_CASES

    if cases is None:
        cases = GOLDEN_CASES

    result = EvalResult()

    # Eval uses `run_trace` (not `run`) so tool-execution errors don't
    # throw away the tool_calls we observed upstream — we're scoring
    # routing decisions, not tool success.
    has_trace = hasattr(agent_runner, "run_trace")

    for i, case in enumerate(cases):
        session_id = f"eval_{i}"
        try:
            if has_trace:
                response, error = await agent_runner.run_trace(
                    user_id=user_id,
                    session_id=session_id,
                    message=case.query,
                )
            else:
                response = await agent_runner.run(
                    user_id=user_id,
                    session_id=session_id,
                    message=case.query,
                )
                error = None
        except Exception as e:
            logger.warning("eval case %d raised: %s", i, e)
            result.cases.append(
                CaseResult(
                    case=case,
                    passed=False,
                    actual_tool_calls=[],
                    response_text="",
                    error=str(e),
                )
            )
            continue

        actual_tool_names = [tc.get("name", "") for tc in response.tool_calls]
        passed = _score_case(case, actual_tool_names)
        result.cases.append(
            CaseResult(
                case=case,
                passed=passed,
                actual_tool_calls=actual_tool_names,
                response_text=response.text,
                error=error,
            )
        )

    return result


def print_report(result: EvalResult) -> None:
    """Print a per-case report to stdout."""
    print()
    print("=" * 72)
    print("GClaw Orchestrator Eval Report")
    print("=" * 72)
    for i, cr in enumerate(result.cases):
        tools = ", ".join(cr.actual_tool_calls) or "(none)"
        expected = ", ".join(cr.case.expected_tools) or "(none)"
        print(f"[{cr.label}] {i:2d}  [{cr.case.category}] {cr.case.description}")
        print(f"       query:     {cr.case.query}")
        print(f"       expected:  {expected}")
        print(f"       actual:    {tools}")
        if cr.error:
            print(f"       error:     {cr.error}")
    print("-" * 72)
    print(f"Summary: {result.summary()}")
    print("=" * 72)
