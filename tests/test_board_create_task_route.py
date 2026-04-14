"""Tests for POST /board/tasks with initial_status + new optional fields."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport

from gclaw.api.app import create_app
from gclaw.auth.dependencies import get_current_user_id
from gclaw.models.task import BoardTask, TaskStatus


async def _override_user_id() -> str:
    return "test_user_1"


@pytest.fixture
def board_service():
    svc = MagicMock()
    svc.create_task.side_effect = lambda **kw: BoardTask(
        title=kw["title"],
        assignee=kw["assignee"],
        status=kw.get("status", TaskStatus.BACKLOG),
    )
    return svc


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
async def test_create_task_defaults_to_queued(client, board_service):
    resp = await client.post(
        "/board/tasks",
        json={"title": "Do the thing", "assignee": "workspace-mgr"},
    )
    assert resp.status_code == 201
    kwargs = board_service.create_task.call_args.kwargs
    assert kwargs["status"] == TaskStatus.QUEUED
    assert kwargs["source_type"] == "user"
    assert kwargs["source_origin"] == "test_user_1"
    assert kwargs["user_id"] == "test_user_1"
    assert kwargs["requires_approval"] is False
    assert kwargs["dependencies"] == []


@pytest.mark.asyncio
async def test_create_task_backlog(client, board_service):
    resp = await client.post(
        "/board/tasks",
        json={
            "title": "Later",
            "assignee": "dev-mgr",
            "initial_status": "backlog",
        },
    )
    assert resp.status_code == 201
    kwargs = board_service.create_task.call_args.kwargs
    assert kwargs["status"] == TaskStatus.BACKLOG


@pytest.mark.asyncio
async def test_create_task_with_approval_and_deps(client, board_service):
    resp = await client.post(
        "/board/tasks",
        json={
            "title": "Gated",
            "assignee": "dev-mgr",
            "requires_approval": True,
            "dependencies": ["task_a", "task_b"],
            "priority": "high",
        },
    )
    assert resp.status_code == 201
    kwargs = board_service.create_task.call_args.kwargs
    assert kwargs["requires_approval"] is True
    assert kwargs["dependencies"] == ["task_a", "task_b"]
    assert kwargs["priority"].value == "high"


@pytest.mark.asyncio
async def test_create_task_invalid_initial_status_rejected(
    client, board_service
):
    resp = await client.post(
        "/board/tasks",
        json={
            "title": "Bad",
            "assignee": "dev-mgr",
            "initial_status": "done",
        },
    )
    assert resp.status_code == 422
    board_service.create_task.assert_not_called()
