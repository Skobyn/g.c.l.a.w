"""Tests for POST /admin/heartbeat/trigger manual-wake endpoint."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from gclaw.api.admin_routes import init_admin_router
from gclaw.heartbeat.events import (
    HeartbeatEvent,
    HeartbeatStatus,
    get_event_bus,
)
from gclaw.heartbeat.reason import WakeReason
from gclaw.heartbeat.registry import HeartbeatRegistry
from gclaw.heartbeat.config import HeartbeatConfig


@pytest.fixture
def _clear_bus():
    get_event_bus()._ring.clear()
    yield
    get_event_bus()._ring.clear()


def _build_app(registry: HeartbeatRegistry | None) -> FastAPI:
    config_loader = MagicMock()
    skill_registry = MagicMock()
    skill_registry.list_all.return_value = []

    app = FastAPI()
    app.include_router(
        init_admin_router(
            config_loader=config_loader,
            heartbeat_log_repo_factory=lambda uid: MagicMock(),
            skill_registry=skill_registry,
            memory_service=AsyncMock(),
            cron_service=MagicMock(),
            heartbeat_registry=registry,
        )
    )
    from gclaw.auth.dependencies import get_current_user_id
    app.dependency_overrides[get_current_user_id] = lambda: "test_user"
    return app


@pytest.mark.asyncio
async def test_trigger_runs_service_with_manual_reason(_clear_bus):
    reg = HeartbeatRegistry()
    svc = AsyncMock()

    async def fake_run(reason=WakeReason.INTERVAL):
        # Emit an event like real HeartbeatService would.
        get_event_bus().emit(
            HeartbeatEvent(
                agent_id="orchestrator",
                status=HeartbeatStatus.SENT,
                reason=reason,
                preview="hello",
            )
        )
        return {
            "orchestrator_response": "hi",
            "actions_taken": ["tool_a"],
            "tasks_created": ["t1"],
            "context": {},
            "status": HeartbeatStatus.SENT,
        }

    svc.run = AsyncMock(side_effect=fake_run)
    reg.register(
        "orchestrator", svc, HeartbeatConfig(enabled=True, every="30m")
    )
    app = _build_app(reg)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.post("/admin/heartbeat/trigger")

    assert resp.status_code == 200, resp.text
    body = resp.json()

    svc.run.assert_awaited_once()
    assert svc.run.await_args.kwargs["reason"] == WakeReason.MANUAL

    assert body["event"] is not None
    assert body["event"]["agent_id"] == "orchestrator"
    assert body["event"]["reason"] == "manual"
    assert body["result"]["orchestrator_response"] == "hi"
    assert body["result"]["actions_taken"] == ["tool_a"]


@pytest.mark.asyncio
async def test_trigger_unknown_agent_returns_404(_clear_bus):
    reg = HeartbeatRegistry()
    app = _build_app(reg)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.post("/admin/heartbeat/trigger?agent_id=nope")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_trigger_without_registry_returns_503(_clear_bus):
    app = _build_app(None)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.post("/admin/heartbeat/trigger")
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_trigger_specific_agent(_clear_bus):
    reg = HeartbeatRegistry()
    svc_o = AsyncMock()
    svc_o.run = AsyncMock(return_value={
        "orchestrator_response": "", "actions_taken": [],
        "tasks_created": [], "context": {}, "status": HeartbeatStatus.OK_EMPTY,
    })
    svc_d = AsyncMock()
    svc_d.run = AsyncMock(return_value={
        "orchestrator_response": "dev", "actions_taken": [],
        "tasks_created": [], "context": {}, "status": HeartbeatStatus.SENT,
    })
    reg.register("orchestrator", svc_o, HeartbeatConfig(enabled=True, every="30m"))
    reg.register("dev-mgr", svc_d, HeartbeatConfig(enabled=True, every="30m"))
    app = _build_app(reg)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.post("/admin/heartbeat/trigger?agent_id=dev-mgr")
    assert resp.status_code == 200
    svc_d.run.assert_awaited_once()
    svc_o.run.assert_not_awaited()
