"""Tests for FastAPI endpoints."""

import pytest
from unittest.mock import MagicMock, AsyncMock
from httpx import AsyncClient, ASGITransport

from gclaw.api.app import create_app
from gclaw.models.task import BoardTask, TaskStatus
from gclaw.dispatch.runner import AgentResponse


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
    return create_app(board_service=board_service, agent_runner=agent_runner)


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
async def test_chat(client, agent_runner):
    agent_runner.run.return_value = AgentResponse(
        text="Hello! I'm GClaw.", is_final=True
    )

    resp = await client.post("/chat", json={
        "user_id": "user_1",
        "session_id": "sess_1",
        "message": "Hello",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["text"] == "Hello! I'm GClaw."
    assert data["is_final"] is True


@pytest.mark.asyncio
async def test_list_board_tasks_empty(client):
    resp = await client.get("/board/tasks", params={"user_id": "user_1"})
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_board_task(client, board_service):
    resp = await client.post("/board/tasks", json={
        "user_id": "user_1",
        "title": "New task",
        "assignee": "workspace-mgr",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "New task"
    board_service.create_task.assert_called_once()
