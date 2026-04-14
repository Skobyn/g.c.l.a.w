"""Tests for POST /board/tasks/{id}/status route."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport

from gclaw.api.app import create_app
from gclaw.auth.dependencies import get_current_user_id
from gclaw.board.transitions import TransitionNotAllowed
from gclaw.models.task import BoardTask, TaskStatus


async def _override_user_id() -> str:
    return "test_user_1"


@pytest.fixture
def board_service():
    return MagicMock()


@pytest.fixture
def app(board_service):
    application = create_app(
        board_service=board_service,
        agent_runner=AsyncMock(),
    )
    application.dependency_overrides[get_current_user_id] = _override_user_id
    return application


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_move_status_success(client, board_service):
    moved = BoardTask(
        id="t1", title="T", assignee="workspace-mgr", status=TaskStatus.QUEUED
    )
    board_service.move_status.return_value = moved

    resp = await client.post(
        "/board/tasks/t1/status", json={"target": "queued"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "queued"
    board_service.move_status.assert_called_once()
    kwargs = board_service.move_status.call_args.kwargs
    assert kwargs["user_id"] == "test_user_1"
    args = board_service.move_status.call_args.args
    assert args[0] == "t1"
    assert args[1] == TaskStatus.QUEUED


@pytest.mark.asyncio
async def test_move_status_forbidden_returns_409(client, board_service):
    board_service.move_status.side_effect = TransitionNotAllowed(
        TaskStatus.BACKLOG, TaskStatus.DONE
    )

    resp = await client.post(
        "/board/tasks/t1/status", json={"target": "done"}
    )
    assert resp.status_code == 409
    assert "backlog" in resp.json()["detail"]
    assert "done" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_move_status_not_found_returns_404(client, board_service):
    board_service.move_status.side_effect = ValueError("Task nope not found")

    resp = await client.post(
        "/board/tasks/nope/status", json={"target": "queued"}
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_move_status_invalid_status_returns_422(client, board_service):
    resp = await client.post(
        "/board/tasks/t1/status", json={"target": "bogus"}
    )
    assert resp.status_code == 422
