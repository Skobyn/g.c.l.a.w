"""Agent-level evaluation harness for GClaw.

Two layers live here:

- **Legacy golden-set runner** (``cases.py`` + ``runner.py``,
  ``__main__.py``): the permissive any-tool-matched scorer driven by
  ``python -m gclaw.eval``. Predates ADR-0005 and is still wired into
  the local manual smoke-test path.
- **Evalset framework** (``evalset.py``, ``evalset_runner.py``,
  ``judge.py``, ``metrics/``): ADR-0005 implementation. Pydantic models
  matching the agents-cli evalset JSON, an LLM-as-judge client with
  per-run caching, and a metric set that scores trajectories and
  responses. Driven by the ``gclaw-eval`` CLI in ``gclaw.cli.eval``.

Both layers can be used independently. The new framework is what CI
will run; the legacy harness stays around for one-shot manual probes.
"""

from gclaw.eval.cases import EvalCase as LegacyEvalCase
from gclaw.eval.cases import GOLDEN_CASES
from gclaw.eval.evalset import (
    EvalCase,
    EvalCaseResult,
    EvalRunResult,
    Evalset,
    ExpectedResponse,
    FinalResponseMatchV2,
    HallucinationsCheck,
    MetricScore,
    ResponseMatch,
    RubricBased,
    RubricBasedToolUse,
    SafetyCheck,
    ToolUseExpectation,
)
from gclaw.eval.evalset_runner import EvalRunner
from gclaw.eval.judge import JudgeClient, JudgeVerdict
from gclaw.eval.runner import CaseResult, EvalResult, run_eval

__all__ = [
    # Legacy harness
    "LegacyEvalCase",
    "GOLDEN_CASES",
    "CaseResult",
    "EvalResult",
    "run_eval",
    # ADR-0005 evalset framework
    "EvalCase",
    "Evalset",
    "EvalCaseResult",
    "EvalRunResult",
    "ExpectedResponse",
    "FinalResponseMatchV2",
    "HallucinationsCheck",
    "MetricScore",
    "ResponseMatch",
    "RubricBased",
    "RubricBasedToolUse",
    "SafetyCheck",
    "ToolUseExpectation",
    "EvalRunner",
    "JudgeClient",
    "JudgeVerdict",
]
