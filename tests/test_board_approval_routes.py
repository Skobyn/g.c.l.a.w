"""Tests for POST /board/tasks/{id}/approve and /reject routes."""

from __future__ import annotations

from datetime import datetime, timezone

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
async def test_approve_success(client, board_service):
    now = datetime.now(timezone.utc)
    approved = BoardTask(
        id="t1",
        title="Needs approval",
        assignee="workspace-mgr",
        status=TaskStatus.QUEUED,
        approved_at=now,
        approved_by="test_user_1",
    )
    board_service.approve.return_value = approved

    resp = await client.post(
        "/board/tasks/t1/approve", json={"note": "looks good"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "queued"
    assert data["approved_by"] == "test_user_1"
    assert data["approved_at"] is not None
    board_service.approve.assert_called_once_with(
        "t1", user_id="test_user_1", note="looks good"
    )


@pytest.mark.asyncio
async def test_approve_without_body_ok(client, board_service):
    approved = BoardTask(
        id="t1",
        title="Needs approval",
        assignee="workspace-mgr",
        status=TaskStatus.QUEUED,
        approved_at=datetime.now(timezone.utc),
        approved_by="test_user_1",
    )
    board_service.approve.return_value = approved

    resp = await client.post("/board/tasks/t1/approve")
    assert resp.status_code == 200
    board_service.approve.assert_called_once_with(
        "t1", user_id="test_user_1", note=None
    )


@pytest.mark.asyncio
async def test_approve_wrong_status_returns_409(client, board_service):
    board_service.approve.side_effect = ValueError(
        "Task t1 is not awaiting approval (status=queued)"
    )
    resp = await client.post("/board/tasks/t1/approve", json={})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_approve_missing_task_returns_404(client, board_service):
    board_service.approve.side_effect = ValueError("Task nope not found")
    resp = await client.post("/board/tasks/nope/approve", json={})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_reject_success(client, board_service):
    now = datetime.now(timezone.utc)
    rejected = BoardTask(
        id="t1",
        title="Needs approval",
        assignee="workspace-mgr",
        status=TaskStatus.FAILED,
        rejected_at=now,
        rejection_note="nope",
    )
    board_service.reject.return_value = rejected

    resp = await client.post(
        "/board/tasks/t1/reject", json={"note": "nope"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "failed"
    assert data["rejection_note"] == "nope"
    assert data["rejected_at"] is not None
    board_service.reject.assert_called_once_with(
        "t1", user_id="test_user_1", note="nope"
    )


@pytest.mark.asyncio
async def test_reject_without_note_returns_422(client, board_service):
    resp = await client.post("/board/tasks/t1/reject", json={})
    assert resp.status_code == 422
    board_service.reject.assert_not_called()


@pytest.mark.asyncio
async def test_reject_empty_note_returns_422(client, board_service):
    resp = await client.post("/board/tasks/t1/reject", json={"note": ""})
    assert resp.status_code == 422
    board_service.reject.assert_not_called()


@pytest.mark.asyncio
async def test_reject_wrong_status_returns_409(client, board_service):
    board_service.reject.side_effect = ValueError(
        "Task t1 is not awaiting approval (status=done)"
    )
    resp = await client.post(
        "/board/tasks/t1/reject", json={"note": "bad"}
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_reject_missing_task_returns_404(client, board_service):
    board_service.reject.side_effect = ValueError("Task nope not found")
    resp = await client.post(
        "/board/tasks/nope/reject", json={"note": "bad"}
    )
    assert resp.status_code == 404
