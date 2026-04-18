"""Admin-only trigger for the nightly Vertex Gen AI scoring job.

POST /admin/scoring/run
    Dispatches a batch of samples to
    :class:`VertexScoringService.score_batch`, returns the scores, and
    optionally persists them via the injected ``results_writer``.
    Designed to be hit on a schedule by Cloud Scheduler (see
    crons/vertex_scoring.json) but safe to invoke manually too.

The sampler is trivial for v1 — the caller passes a list of already-
collected samples. A follow-up will build the ``SpanSampler`` that
drains a recent Phoenix window and stratifies by agent name.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from gclaw.auth.dependencies import get_current_user_id
from gclaw.eval.vertex_scoring_service import ScoringSample, VertexScoringService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["scoring"])

_scorer: VertexScoringService | None = None
_results_writer: Any | None = None  # Callable[[ScoringResult], None]


def init_scoring_router(
    *,
    scorer: VertexScoringService,
    results_writer: Any | None = None,
) -> APIRouter:
    """Wire the router. ``results_writer`` is optional; when None, the
    endpoint returns scores in the response body but doesn't persist."""
    global _scorer, _results_writer
    _scorer = scorer
    _results_writer = results_writer
    return router


class ScoringSampleBody(BaseModel):
    span_id: str
    response: str
    context: str | None = None
    reference: str | None = None


class ScoringRunRequest(BaseModel):
    samples: list[ScoringSampleBody] = Field(default_factory=list)


@router.post("/scoring/run")
async def trigger_scoring(
    body: ScoringRunRequest,
    _user_id: str = Depends(get_current_user_id),  # noqa: B008
) -> dict:
    if _scorer is None:
        raise HTTPException(
            status_code=503, detail="Vertex scoring service not configured"
        )
    if not _scorer.enabled:
        return {
            "enabled": False,
            "available": False,
            "sampled": 0,
            "results": [],
        }

    samples = [
        ScoringSample(
            span_id=s.span_id,
            response=s.response,
            context=s.context,
            reference=s.reference,
        )
        for s in body.samples
    ]
    results = await _scorer.score_batch(samples)

    if _results_writer is not None:
        for r in results:
            try:
                _results_writer(r)
            except Exception:
                logger.warning(
                    "scoring: results_writer failed for %s",
                    r.span_id,
                    exc_info=True,
                )

    return {
        "enabled": True,
        "available": _scorer.is_available(),
        "sampled": len(results),
        "results": [r.to_firestore_dict() for r in results],
    }
