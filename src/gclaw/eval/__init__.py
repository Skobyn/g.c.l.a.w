"""Agent-level evaluation harness for GClaw.

This package is the minimum-viable eval layer that scores live
orchestrator runs against golden input/output pairs. Unlike the 411
unit tests that verify wiring, the eval harness verifies *behaviour* —
does the orchestrator actually route "draft an email" to comms-mgr?

The case format is intentionally shaped to map cleanly onto Vertex AI
Gen AI Evaluation Service `EvalDataset` schemas, so this harness is
the upgrade path to SDK-based eval rather than a dead end.

Entry points:

- `gclaw.eval.cases.GOLDEN_CASES` — the baseline case list.
- `gclaw.eval.runner.run_eval(agent_runner, cases)` — score cases.
- `python -m gclaw.eval` — build the real orchestrator and run the
  golden set end-to-end. Hits live Gemini, costs real tokens.
"""

from gclaw.eval.cases import EvalCase, GOLDEN_CASES
from gclaw.eval.runner import CaseResult, EvalResult, run_eval

__all__ = [
    "EvalCase",
    "GOLDEN_CASES",
    "CaseResult",
    "EvalResult",
    "run_eval",
]
