"""Tests for admin heartbeat events/health endpoints."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from gclaw.api.admin_routes import init_admin_router
from gclaw.heartbeat.events import (
    HeartbeatEvent,
    HeartbeatStatus,
    get_event_bus,
)
from gclaw.heartbeat.reason import WakeReason


@pytest.fixture
def admin_app():
    config_loader = MagicMock()
    heartbeat_log_repo = MagicMock()
    heartbeat_log_repo.list_recent.return_value = []
    skill_registry = MagicMock()
    skill_registry.list_all.return_value = []
    memory_service = AsyncMock()
    cron_service = MagicMock()

    app = FastAPI()
    app.include_router(
        init_admin_router(
            config_loader=config_loader,
            heartbeat_log_repo_factory=lambda uid: heartbeat_log_repo,
            skill_registry=skill_registry,
            memory_service=memory_service,
            cron_service=cron_service,
        )
    )
    from gclaw.auth.dependencies import get_current_user_id
    app.dependency_overrides[get_current_user_id] = lambda: "test_user"

    # Clear the singleton ring buffer so tests don't see leakage.
    bus = get_event_bus()
    bus._ring.clear()
    return app


@pytest.fixture
async def admin_client(admin_app):
    transport = ASGITransport(app=admin_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_events_endpoint_returns_recent_events(admin_client):
    bus = get_event_bus()
    bus.emit(
        HeartbeatEvent(
            agent_id="orchestrator",
            status=HeartbeatStatus.SENT,
            reason=WakeReason.INTERVAL,
            duration_ms=12,
            preview="hello world",
        )
    )
    bus.emit(
        HeartbeatEvent(
            agent_id="dev-mgr",
            status=HeartbeatStatus.FAILED,
            reason=WakeReason.MANUAL,
            duration_ms=3,
            error="boom",
        )
    )

    resp = await admin_client.get("/admin/heartbeat/events")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    # newest first
    assert body[0]["agent_id"] == "dev-mgr"
    assert body[0]["status"] == "failed"
    assert body[0]["error"] == "boom"
    assert body[1]["preview"] == "hello world"


@pytest.mark.asyncio
async def test_events_endpoint_filters_by_agent_id(admin_client):
    bus = get_event_bus()
    bus.emit(
        HeartbeatEvent(
            agent_id="orchestrator",
            status=HeartbeatStatus.SENT,
            reason=WakeReason.INTERVAL,
        )
    )
    bus.emit(
        HeartbeatEvent(
            agent_id="dev-mgr",
            status=HeartbeatStatus.SENT,
            reason=WakeReason.INTERVAL,
        )
    )
    resp = await admin_client.get("/admin/heartbeat/events?agent_id=dev-mgr")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["agent_id"] == "dev-mgr"


@pytest.mark.asyncio
async def test_health_endpoint_summarizes_per_agent(admin_client):
    bus = get_event_bus()
    bus.emit(
        HeartbeatEvent(
            agent_id="orchestrator",
            status=HeartbeatStatus.SENT,
            reason=WakeReason.INTERVAL,
            preview="first",
        )
    )
    bus.emit(
        HeartbeatEvent(
            agent_id="orchestrator",
            status=HeartbeatStatus.FAILED,
            reason=WakeReason.MANUAL,
            preview="second",
            error="x",
        )
    )
    bus.emit(
        HeartbeatEvent(
            agent_id="dev-mgr",
            status=HeartbeatStatus.SENT,
            reason=WakeReason.CRON,
            preview="devm",
        )
    )

    resp = await admin_client.get("/admin/heartbeat/health")
    assert resp.status_code == 200
    body = resp.json()
    agents = {a["agent_id"]: a for a in body["agents"]}
    assert set(agents.keys()) == {"orchestrator", "dev-mgr"}
    # most recent orchestrator event wins
    assert agents["orchestrator"]["last_status"] == "failed"
    assert agents["orchestrator"]["last_reason"] == "manual"
    assert agents["orchestrator"]["last_preview"] == "second"
    assert agents["dev-mgr"]["last_status"] == "sent"
    assert agents["dev-mgr"]["last_reason"] == "cron"
