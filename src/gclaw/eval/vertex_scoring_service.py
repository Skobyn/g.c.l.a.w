"""Vertex AI Gen AI Evaluation — nightly async quality scoring.

Wraps ``google-cloud-aiplatform``'s ``vertexai.preview.evaluation``
module to score sampled production spans for groundedness, coherence,
and tool-use correctness. Fail-soft everywhere — an SDK version mismatch
or transient Vertex outage must not crash the background job.

The class is structured so tests can inject a fake SDK (``_client``) and
exercise the orchestration without talking to Vertex. At runtime the
client is lazily resolved; if the SDK is unavailable we record
``available=False`` and every ``score_batch`` call returns an empty
list with a warning — consistent with the Phase 1 pattern of keeping
the feature OFF-by-default.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ScoringSample:
    """One input to the scoring pipeline. Matches a single agent turn."""

    span_id: str
    response: str
    context: str | None = None
    reference: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScoringResult:
    span_id: str
    scores: dict[str, float] = field(default_factory=dict)
    error: str | None = None

    def to_firestore_dict(self) -> dict[str, Any]:
        return {
            "span_id": self.span_id,
            "scores": self.scores,
            "error": self.error,
        }


class VertexScoringService:
    """Thin async wrapper over Vertex Gen AI Evaluation.

    Construction is lazy and safe even without the SDK installed.
    """

    DEFAULT_METRICS = ("groundedness", "coherence", "tool_use_quality")

    def __init__(
        self,
        *,
        project: str | None = None,
        location: str = "us-central1",
        metrics: tuple[str, ...] = DEFAULT_METRICS,
        enabled: bool = False,
        client: Any | None = None,
    ) -> None:
        self._project = project
        self._location = location
        self._metrics = metrics
        self._enabled = enabled
        self._client = client  # injected for tests
        self._available: bool | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled and self._project is not None

    def is_available(self) -> bool:
        if not self.enabled:
            return False
        if self._available is not None:
            return self._available
        if self._client is not None:
            self._available = True
            return True
        try:
            # Lazy import — keeps boot-time cheap and survives SDK absence.
            from vertexai.preview.evaluation import EvalTask  # noqa: F401
            self._available = True
        except Exception:
            logger.warning(
                "vertex_scoring: SDK unavailable; scoring disabled. "
                "Install google-cloud-aiplatform>=1.60 to enable."
            )
            self._available = False
        return self._available

    async def score_batch(
        self, samples: list[ScoringSample]
    ) -> list[ScoringResult]:
        if not samples:
            return []
        if not self.is_available():
            return [
                ScoringResult(
                    span_id=s.span_id, error="vertex scoring unavailable"
                )
                for s in samples
            ]
        return await asyncio.to_thread(self._score_sync, samples)

    # ── internal ───────────────────────────────────────────────────────

    def _score_sync(
        self, samples: list[ScoringSample]
    ) -> list[ScoringResult]:
        client = self._client or self._build_client()
        results: list[ScoringResult] = []
        for sample in samples:
            try:
                scores = client.score(
                    response=sample.response,
                    context=sample.context,
                    reference=sample.reference,
                    metrics=list(self._metrics),
                )
                results.append(
                    ScoringResult(
                        span_id=sample.span_id,
                        scores={k: float(v) for k, v in (scores or {}).items()},
                    )
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "vertex_scoring: score() failed for %s: %s",
                    sample.span_id,
                    e,
                )
                results.append(
                    ScoringResult(span_id=sample.span_id, error=str(e))
                )
        return results

    def _build_client(self) -> Any:
        """Lazy SDK wiring — wrapped in its own method so tests can stub."""
        # Import deferred so boot doesn't pay the aiplatform import cost.
        import vertexai
        from vertexai.preview.evaluation import EvalTask

        vertexai.init(project=self._project, location=self._location)

        class _Adapter:
            def __init__(self, metrics: list[str]) -> None:
                self._metrics = metrics

            def score(
                self,
                *,
                response: str,
                context: str | None,
                reference: str | None,
                metrics: list[str],
            ) -> dict[str, float]:
                import pandas as pd

                df = pd.DataFrame(
                    [
                        {
                            "response": response,
                            "context": context or "",
                            "reference": reference or "",
                        }
                    ]
                )
                task = EvalTask(dataset=df, metrics=metrics)
                summary = task.evaluate()
                row = (summary.metrics_table or df).iloc[0].to_dict()
                return {
                    m: float(row.get(m, 0.0))
                    for m in metrics
                    if m in row
                }

        return _Adapter(list(self._metrics))
