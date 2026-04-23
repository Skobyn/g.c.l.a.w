"""Evalset runner — drives an AgentFactory through every case in an
``Evalset`` and aggregates per-metric scores (ADR-0005).

This sits one level above the legacy ``gclaw.eval.runner`` (which is a
permissive any-tool-matched scorer used by ``python -m gclaw.eval``).
The new runner is structured around the agents-cli-compatible JSON
schema and the metric set in ``gclaw.eval.metrics``.

Typical use::

    factory = AgentFactory(config_loader)
    runner = EvalRunner(factory)
    evalset = Evalset.from_json("tests/eval/evalsets/research-mgr.json")
    out = await runner.run_evalset(evalset)
    out.to_json("tests/eval/results/2026-04-22T22-30-00.json")
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from google.adk.sessions import InMemorySessionService

from gclaw.dispatch.runner import AgentRunner
from gclaw.eval.evalset import (
    EvalCase,
    EvalCaseResult,
    EvalRunResult,
    Evalset,
    MetricScore,
)
from gclaw.eval.judge import JudgeClient
from gclaw.eval.metrics import METRICS

if TYPE_CHECKING:
    from gclaw.agents.factory import AgentFactory

logger = logging.getLogger(__name__)


# Type alias for the factory hook. The CLI uses an AgentFactory; tests
# can pass any callable ``(case) -> AgentRunner`` that returns a
# pre-built runner.
AgentRunnerBuilder = Callable[[EvalCase], AgentRunner]


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class EvalRunner:
    """Run an evalset against agents constructed by an AgentFactory."""

    def __init__(
        self,
        factory: "AgentFactory | None" = None,
        *,
        judge: JudgeClient | None = None,
        session_service: Any | None = None,
        app_name: str = "gclaw-eval",
        runner_builder: AgentRunnerBuilder | None = None,
    ) -> None:
        if factory is None and runner_builder is None:
            raise ValueError(
                "EvalRunner needs either an AgentFactory or a runner_builder"
            )
        self._factory = factory
        self._judge = judge
        self._session_service = session_service or InMemorySessionService()
        self._app_name = app_name
        self._runner_builder = runner_builder

    @property
    def judge(self) -> JudgeClient | None:
        return self._judge

    # ── runner construction ────────────────────────────────────────────

    def _build_runner_for_case(self, case: EvalCase) -> AgentRunner:
        """Build a fresh ``AgentRunner`` for a single case.

        Tests inject a ``runner_builder`` to skip ADK construction. In
        production we lean on the supplied ``AgentFactory`` and only
        attach ``session_service`` — memory/board/usage are intentionally
        unset so the eval doesn't depend on Firestore.
        """
        if self._runner_builder is not None:
            return self._runner_builder(case)

        agent = self._factory.build(case.agent_name)
        return AgentRunner(
            agent=agent,
            app_name=self._app_name,
            session_service=self._session_service,
        )

    # ── per-case execution ─────────────────────────────────────────────

    async def _execute_case(self, case: EvalCase) -> EvalCaseResult:
        """Drive one case through the agent and return the raw trajectory.

        Uses ``run_trace`` when available (preserves partial trajectories
        on tool errors); falls back to ``run`` otherwise.
        """
        runner = self._build_runner_for_case(case)
        session_id = f"eval-{case.case_id}-{uuid.uuid4().hex[:8]}"
        start = time.perf_counter()

        response = None
        error: str | None = None
        try:
            if hasattr(runner, "run_trace"):
                response, error = await runner.run_trace(
                    user_id=case.user_id,
                    session_id=session_id,
                    message=case.input,
                )
            else:
                response = await runner.run(
                    user_id=case.user_id,
                    session_id=session_id,
                    message=case.input,
                )
        except Exception as e:  # noqa: BLE001
            logger.warning("eval case %s raised: %s", case.case_id, e)
            error = f"{type(e).__name__}: {e}"

        duration_ms = int((time.perf_counter() - start) * 1000)
        return EvalCaseResult(
            case_id=case.case_id,
            agent_name=case.agent_name,
            input=case.input,
            response_text=getattr(response, "text", "") or "",
            tool_calls=list(getattr(response, "tool_calls", []) or []),
            error=error,
            duration_ms=duration_ms,
        )

    async def _score_case(
        self, case: EvalCase, raw: EvalCaseResult
    ) -> EvalCaseResult:
        """Apply every applicable metric to a captured trajectory."""
        scores: list[MetricScore] = []
        for name, scorer in METRICS.items():
            try:
                score = await scorer(case, raw, self._judge)
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "metric %s raised on case %s: %s",
                    name,
                    case.case_id,
                    e,
                )
                scores.append(
                    MetricScore(
                        metric=name,
                        score=0.0,
                        rationale=f"metric error: {type(e).__name__}: {e}",
                    )
                )
                continue
            if score is not None:
                scores.append(score)
        raw.metrics = scores
        return raw

    # ── public API ─────────────────────────────────────────────────────

    async def run_evalset(self, evalset: Evalset) -> EvalRunResult:
        """Execute every case and return the aggregated result."""
        # Wire up a default judge once per run if the caller didn't pass one,
        # so all rubric metrics share the same cache.
        if self._judge is None:
            self._judge = JudgeClient(model_name=evalset.judge_model)

        started_at = _utc_iso()
        case_results: list[EvalCaseResult] = []
        for case in evalset.cases:
            raw = await self._execute_case(case)
            scored = await self._score_case(case, raw)
            case_results.append(scored)
        finished_at = _utc_iso()

        # Per-metric averages (only over cases where the metric applied).
        per_metric: dict[str, list[float]] = {}
        for cr in case_results:
            for m in cr.metrics:
                per_metric.setdefault(m.metric, []).append(m.score)
        averages = {
            name: sum(scores) / len(scores)
            for name, scores in per_metric.items()
            if scores
        }

        return EvalRunResult(
            evalset_name=evalset.name,
            started_at=started_at,
            finished_at=finished_at,
            judge_model=evalset.judge_model,
            cases=case_results,
            metric_averages=averages,
        )

    async def run_and_save(
        self,
        evalset: Evalset,
        results_dir: str | Path = "tests/eval/results",
    ) -> tuple[EvalRunResult, Path]:
        """Run an evalset and persist the result to ``results_dir``.

        Filename: ``<evalset_name>-<UTC timestamp>.json``, with a short
        random suffix appended when a same-second collision is detected
        (so back-to-back ``run --all`` invocations don't clobber each
        other's output).
        """
        result = await self.run_evalset(evalset)
        # Filesystem-safe ISO timestamp. Replace the timezone first so
        # the ``:`` substitution doesn't smear ``+00:00`` into ``+00-00``.
        stamp = result.finished_at.replace("+00:00", "Z").replace(":", "-")
        out_dir = Path(results_dir)
        out_path = out_dir / f"{evalset.name}-{stamp}.json"
        if out_path.exists():
            out_path = (
                out_dir / f"{evalset.name}-{stamp}-{uuid.uuid4().hex[:6]}.json"
            )
        result.to_json(out_path)
        return result, out_path
