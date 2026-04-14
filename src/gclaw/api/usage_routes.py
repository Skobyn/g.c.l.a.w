"""Admin API routes for unified usage telemetry."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from gclaw.auth.dependencies import get_current_user_id
from gclaw.firestore.usage_repo import UsageRepo
from gclaw.models.usage import UsageKind

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/usage")

_usage_repo: UsageRepo | None = None


def init_usage_router(usage_repo: UsageRepo | None) -> APIRouter:
    global _usage_repo
    _usage_repo = usage_repo
    return router


def _require_repo() -> UsageRepo:
    if _usage_repo is None:
        raise HTTPException(
            status_code=503, detail="Usage telemetry not configured"
        )
    return _usage_repo


def _parse_since(since: str | None, default_hours: int = 24) -> datetime:
    if since:
        try:
            dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid since= value: {since!r}",
            )
    return datetime.now(timezone.utc) - timedelta(hours=default_hours)


@router.get("/events")
def list_events(
    kind: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    since: str | None = None,
    user_id: str = Depends(get_current_user_id),
):
    """List recent usage events, newest first."""
    repo = _require_repo()
    kind_enum: UsageKind | None = None
    if kind:
        try:
            kind_enum = UsageKind(kind)
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Unknown kind: {kind!r}"
            )
    since_dt = _parse_since(since, default_hours=24 * 7) if since else None
    events = repo.list_recent(
        limit=limit, kind=kind_enum, since=since_dt, user_id=user_id
    )
    return [e.model_dump(mode="json") for e in events]


@router.get("/summary")
def summary(
    since: str | None = None,
    top_n: int = Query(20, ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
):
    """Aggregated rollup across the four usage kinds."""
    repo = _require_repo()
    since_dt = _parse_since(since, default_hours=24)

    # Per-kind top-N aggregations
    models = repo.aggregate_by_name(
        UsageKind.MODEL, since_dt, limit=top_n, user_id=user_id
    )
    agents = repo.aggregate_by_name(
        UsageKind.AGENT, since_dt, limit=top_n, user_id=user_id
    )
    skills = repo.aggregate_by_name(
        UsageKind.SKILL, since_dt, limit=top_n, user_id=user_id
    )
    tools = repo.aggregate_by_name(
        UsageKind.TOOL, since_dt, limit=top_n, user_id=user_id
    )

    totals = {
        "model": sum(r["count"] for r in models),
        "agent": sum(r["count"] for r in agents),
        "skill": sum(r["count"] for r in skills),
        "tool": sum(r["count"] for r in tools),
        "total_cost_usd": round(
            sum(r["cost_usd"] for r in models), 6
        ),
    }

    timeseries = repo.aggregate_by_hour(since_dt, user_id=user_id)

    return {
        "totals": totals,
        "top": {
            "models": [
                {
                    "name": r["name"],
                    "count": r["count"],
                    "tokens_in": r["tokens_in"],
                    "tokens_out": r["tokens_out"],
                    "cost_usd": r["cost_usd"],
                }
                for r in models
            ],
            "agents": [
                {
                    "name": r["name"],
                    "count": r["count"],
                    "avg_duration_ms": r["avg_duration_ms"],
                    "failure_rate": round(r["failure_rate"], 4),
                }
                for r in agents
            ],
            "skills": [
                {"name": r["name"], "count": r["count"]}
                for r in skills
            ],
            "tools": [
                {
                    "name": r["name"],
                    "count": r["count"],
                    "failure_rate": round(r["failure_rate"], 4),
                }
                for r in tools
            ],
        },
        "timeseries": timeseries,
    }
