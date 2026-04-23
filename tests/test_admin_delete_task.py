"""Tests for DELETE /admin/board/tasks/{id} and bulk-delete."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from gclaw.api.admin_routes import init_admin_router
from gclaw.models.task import BoardTask, TaskStatus


@pytest.fixture
def admin_app():
    board = MagicMock()

    app = FastAPI()
    app.include_router(
        init_admin_router(
            config_loader=MagicMock(),
            skill_registry=MagicMock(),
            board_service=board,
        )
    )
    from gclaw.auth.dependencies import get_current_user_id
    app.dependency_overrides[get_current_user_id] = lambda: "test_user"
    return app, board


# ── single delete ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_task_removes_row(admin_app):
    app, board = admin_app
    board.delete_task.return_value = True

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.delete("/admin/board/tasks/task_x")
    assert resp.status_code == 200
    assert resp.json() == {"status": "deleted", "task_id": "task_x"}
    board.delete_task.assert_called_once_with("task_x", user_id="test_user")


@pytest.mark.asyncio
async def test_delete_task_404_when_missing(admin_app):
    app, board = admin_app
    board.delete_task.return_value = False

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.delete("/admin/board/tasks/nope")
    assert resp.status_code == 404


# ── bulk delete ────────────────────────────────────────────────────


def _mk(id: str, assignee: str, status: TaskStatus, title: str = "x") -> BoardTask:
    return BoardTask(id=id, title=title, assignee=assignee, status=status)


@pytest.mark.asyncio
async def test_bulk_delete_by_status(admin_app):
    app, board = admin_app
    board.get_all_tasks.return_value = [
        _mk("a", "research-mgr", TaskStatus.BACKLOG),
        _mk("b", "research-mgr", TaskStatus.BACKLOG),
        _mk("c", "research-mgr", TaskStatus.QUEUED),  # should NOT delete
    ]
    board.delete_task.side_effect = lambda tid, user_id: True

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.post(
            "/admin/board/tasks/bulk-delete",
            json={"status_in": ["backlog"]},
        )
    body = resp.json()
    assert resp.status_code == 200
    assert body["deleted_count"] == 2
    assert sorted(body["deleted_ids"]) == ["a", "b"]


@pytest.mark.asyncio
async def test_bulk_delete_by_assignee_and_title(admin_app):
    app, board = admin_app
    board.get_all_tasks.return_value = [
        _mk("a", "research-mgr", TaskStatus.BACKLOG, "Research Google Next"),
        _mk("b", "research-mgr", TaskStatus.BACKLOG, "Research capabilities of cli"),
        _mk("c", "dev-mgr", TaskStatus.BACKLOG, "Research Google Next"),
    ]
    board.delete_task.side_effect = lambda tid, user_id: True

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.post(
            "/admin/board/tasks/bulk-delete",
            json={"assignee": "research-mgr", "title_contains": "Google Next"},
        )
    body = resp.json()
    assert resp.status_code == 200
    # Only the research-mgr task whose title contains "Google Next".
    assert body["deleted_ids"] == ["a"]


@pytest.mark.asyncio
async def test_bulk_delete_refuses_empty_filter(admin_app):
    app, board = admin_app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.post("/admin/board/tasks/bulk-delete", json={})
    assert resp.status_code == 400
    board.get_all_tasks.assert_not_called()
