"""Admin usage routes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gclaw.api.usage_routes import init_usage_router
from gclaw.models.usage import UsageEvent, UsageKind


def _app(repo):
    app = FastAPI()

    @app.middleware("http")
    async def set_user(request, call_next):
        request.state.user_id = "u1"
        return await call_next(request)

    app.include_router(init_usage_router(repo))
    return app


@pytest.fixture
def repo():
    return MagicMock()


def test_events_endpoint_filters_kind(repo):
    repo.list_recent.return_value = [
        UsageEvent(kind=UsageKind.MODEL, name="flash", tokens_in=1, tokens_out=2),
    ]
    client = TestClient(_app(repo))
    r = client.get("/admin/usage/events?kind=model&limit=10")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["kind"] == "model"
    # Ensure kind filter propagated
    call_kwargs = repo.list_recent.call_args.kwargs
    assert call_kwargs["kind"] == UsageKind.MODEL
    assert call_kwargs["limit"] == 10
    assert call_kwargs["user_id"] == "u1"


def test_events_endpoint_rejects_bad_kind(repo):
    client = TestClient(_app(repo))
    r = client.get("/admin/usage/events?kind=banana")
    assert r.status_code == 400


def test_events_endpoint_503_without_repo():
    client = TestClient(_app(None))
    r = client.get("/admin/usage/events")
    assert r.status_code == 503


def test_summary_endpoint_aggregates(repo):
    # Return different aggregations per kind via side_effect
    def fake_agg(kind, since, limit=20, user_id=None):
        if kind == UsageKind.MODEL:
            return [{
                "name": "flash", "count": 5, "tokens_in": 100,
                "tokens_out": 50, "cost_usd": 0.25,
                "avg_duration_ms": 120, "failure_rate": 0.0,
            }]
        if kind == UsageKind.AGENT:
            return [{
                "name": "orchestrator", "count": 4, "tokens_in": 0,
                "tokens_out": 0, "cost_usd": 0.0, "avg_duration_ms": 800,
                "failure_rate": 0.25,
            }]
        if kind == UsageKind.SKILL:
            return [{
                "name": "email-drafter", "count": 2, "tokens_in": 0,
                "tokens_out": 0, "cost_usd": 0.0, "avg_duration_ms": 0,
                "failure_rate": 0.0,
            }]
        if kind == UsageKind.TOOL:
            return [{
                "name": "create_board_task", "count": 3, "tokens_in": 0,
                "tokens_out": 0, "cost_usd": 0.0, "avg_duration_ms": 5,
                "failure_rate": 0.0,
            }]
        return []

    repo.aggregate_by_name.side_effect = fake_agg
    repo.aggregate_by_hour.return_value = [
        {"hour_iso": "2026-04-14T10:00:00+00:00", "model_count": 5,
         "agent_count": 4, "skill_count": 2, "tool_count": 3, "cost_usd": 0.25},
    ]

    client = TestClient(_app(repo))
    r = client.get("/admin/usage/summary?top_n=10")
    assert r.status_code == 200
    body = r.json()
    assert body["totals"] == {
        "model": 5, "agent": 4, "skill": 2, "tool": 3,
        "total_cost_usd": 0.25,
    }
    assert body["top"]["models"][0]["name"] == "flash"
    assert body["top"]["agents"][0]["failure_rate"] == 0.25
    assert body["top"]["skills"][0]["name"] == "email-drafter"
    assert body["top"]["tools"][0]["name"] == "create_board_task"
    assert len(body["timeseries"]) == 1


def test_summary_default_since_24h(repo):
    repo.aggregate_by_name.return_value = []
    repo.aggregate_by_hour.return_value = []
    client = TestClient(_app(repo))
    r = client.get("/admin/usage/summary")
    assert r.status_code == 200
    # first positional `since` param of aggregate_by_name should be ~24h ago
    first_call = repo.aggregate_by_name.call_args_list[0]
    since = first_call.args[1]
    delta = datetime.now(timezone.utc) - since
    assert timedelta(hours=23) < delta < timedelta(hours=25)
