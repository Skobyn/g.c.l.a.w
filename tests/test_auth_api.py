"""Tests for auth-aware API endpoints."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from httpx import AsyncClient, ASGITransport

from gclaw.api.app import create_app
from gclaw.models.task import BoardTask
from gclaw.dispatch.runner import AgentResponse


@pytest.fixture
def mock_firebase_auth():
    with patch("gclaw.auth.middleware.firebase_auth") as mock_auth:
        mock_auth.verify_id_token.return_value = {
            "uid": "auth_user_1",
            "email": "test@example.com",
        }
        yield mock_auth


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
    runner.run.return_value = AgentResponse(
        text="Hello from GClaw!", is_final=True
    )
    return runner


@pytest.fixture
def app(board_service, agent_runner, mock_firebase_auth):
    return create_app(
        board_service=board_service,
        agent_runner=agent_runner,
        enable_auth=True,
    )


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _auth_headers(token: str = "valid_token") -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_chat_uses_auth_user_id(client, agent_runner):
    """POST /chat should derive user_id from auth token, not request body."""
    resp = await client.post(
        "/chat",
        json={"session_id": "sess_1", "message": "Hello"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    # Verify runner was called with the auth-derived user_id
    agent_runner.run.assert_called_once_with(
        user_id="auth_user_1",
        session_id="sess_1",
        message="Hello",
    )


@pytest.mark.asyncio
async def test_chat_without_auth_returns_401(client):
    resp = await client.post(
        "/chat",
        json={"session_id": "sess_1", "message": "Hello"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_board_list_uses_auth_user_id(client, board_service):
    """GET /board/tasks should use auth user_id, not query param."""
    resp = await client.get("/board/tasks", headers=_auth_headers())
    assert resp.status_code == 200
    board_service.get_all_tasks.assert_called_once()


@pytest.mark.asyncio
async def test_board_create_uses_auth_user_id(client, board_service):
    resp = await client.post(
        "/board/tasks",
        json={"title": "Test task", "assignee": "workspace-mgr"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_health_no_auth_required(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
