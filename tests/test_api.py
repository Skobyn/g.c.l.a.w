"""Tests for FastAPI endpoints (auth disabled mode)."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock
from httpx import AsyncClient, ASGITransport
from starlette.requests import Request

from gclaw.api.app import create_app
from gclaw.auth.dependencies import get_current_user_id
from gclaw.models.task import BoardTask, TaskStatus
from gclaw.dispatch.runner import AgentResponse


async def _override_user_id() -> str:
    """Provide a test user_id when auth middleware is disabled."""
    return "test_user_1"


@pytest.fixture
def board_service():
    svc = MagicMock()
    svc.get_all_tasks.return_value = []
    svc.create_task.side_effect = lambda **kw: BoardTask(
        title=kw["title"], assignee=kw["assignee"]
    )
    return svc


@pytest.fixture
def agent_runner():
    runner = AsyncMock()
    return runner


@pytest.fixture
def app(board_service, agent_runner):
    application = create_app(
        board_service=board_service,
        agent_runner=agent_runner,
    )
    # Override the auth dependency for tests without auth middleware
    application.dependency_overrides[get_current_user_id] = _override_user_id
    return application


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_root_landing(client):
    """GET / returns a small JSON pointing visitors at the API
    explorer instead of FastAPI's default 404."""
    resp = await client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "GClaw"
    assert data["docs"] == "/docs"
    assert data["health"] == "/health"
    assert "chat" in data


@pytest.mark.asyncio
async def test_chat(client, agent_runner):
    agent_runner.run.return_value = AgentResponse(
        text="Hello! I'm GClaw.", is_final=True
    )

    resp = await client.post("/chat", json={
        "session_id": "sess_1",
        "message": "Hello",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["text"] == "Hello! I'm GClaw."
    assert data["is_final"] is True


@pytest.mark.asyncio
async def test_chat_end(client, agent_runner):
    agent_runner.end_session = AsyncMock(return_value=None)

    resp = await client.post("/chat/end", json={"session_id": "sess_1"})

    assert resp.status_code == 204
    agent_runner.end_session.assert_awaited_once_with(
        user_id="test_user_1", session_id="sess_1"
    )


@pytest.mark.asyncio
async def test_heartbeat_route_wired(board_service, agent_runner):
    """When a HeartbeatService is passed to create_app, POST /heartbeat
    should invoke its run() method and return 200."""
    heartbeat_service = AsyncMock()
    heartbeat_service.run.return_value = {
        "orchestrator_response": "All quiet.",
        "actions_taken": [],
        "tasks_created": [],
        "context": {"board_summary": {"in_progress": 0}},
    }

    application = create_app(
        board_service=board_service,
        agent_runner=agent_runner,
        heartbeat_service=heartbeat_service,
    )
    application.dependency_overrides[get_current_user_id] = _override_user_id

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/heartbeat")

    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"
    heartbeat_service.run.assert_awaited_once()


@pytest.mark.asyncio
async def test_heartbeat_route_absent_when_service_none(board_service, agent_runner):
    """When no HeartbeatService is passed, POST /heartbeat returns 404
    (route is not mounted)."""
    application = create_app(
        board_service=board_service,
        agent_runner=agent_runner,
        heartbeat_service=None,
    )
    application.dependency_overrides[get_current_user_id] = _override_user_id

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/heartbeat")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_board_tasks_empty(client):
    resp = await client.get("/board/tasks")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_board_task(client, board_service):
    resp = await client.post("/board/tasks", json={
        "title": "New task",
        "assignee": "workspace-mgr",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "New task"
    board_service.create_task.assert_called_once()
