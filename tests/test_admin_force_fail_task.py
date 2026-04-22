"""Tests for the admin break-glass force-fail endpoint."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from gclaw.api.admin_routes import init_admin_router
from gclaw.board.transitions import TransitionNotAllowed
from gclaw.models.task import BoardTask, TaskStatus


@pytest.fixture
def admin_app_with_board():
    board_service = MagicMock()

    app = FastAPI()
    app.include_router(
        init_admin_router(
            config_loader=MagicMock(),
            skill_registry=MagicMock(),
            board_service=board_service,
        )
    )
    from gclaw.auth.dependencies import get_current_user_id
    app.dependency_overrides[get_current_user_id] = lambda: "test_user"

    return app, board_service


@pytest.mark.asyncio
async def test_force_fail_marks_task_failed(admin_app_with_board):
    app, board_service = admin_app_with_board
    task = BoardTask(
        id="t1", title="stuck", assignee="research-mgr",
        status=TaskStatus.FAILED,  # the post-fail shape returned by service
    )
    board_service.fail.return_value = task

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/admin/board/tasks/t1/force-fail",
            json={"reason": "heartbeat timed out"},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "failed"
    board_service.fail.assert_called_once_with(
        "t1", reason="heartbeat timed out", user_id="test_user"
    )


@pytest.mark.asyncio
async def test_force_fail_uses_default_reason_when_body_omitted(
    admin_app_with_board,
):
    app, board_service = admin_app_with_board
    board_service.fail.return_value = BoardTask(
        id="t1", title="x", assignee="a", status=TaskStatus.FAILED,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/admin/board/tasks/t1/force-fail", json={})

    assert resp.status_code == 200
    board_service.fail.assert_called_once()
    kwargs = board_service.fail.call_args.kwargs
    assert "force-failed" in kwargs["reason"]


@pytest.mark.asyncio
async def test_force_fail_404_when_task_missing(admin_app_with_board):
    app, board_service = admin_app_with_board
    board_service.fail.side_effect = ValueError("Task t1 not found")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/admin/board/tasks/t1/force-fail", json={"reason": "x"}
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_force_fail_409_when_transition_illegal(admin_app_with_board):
    """DONE and BACKLOG/QUEUED states don't permit IN_PROGRESS → FAILED
    through the service — the model layer rejects it. Surface 409 so
    admins know this wasn't a route bug."""
    app, board_service = admin_app_with_board
    board_service.fail.side_effect = TransitionNotAllowed(
        TaskStatus.DONE, TaskStatus.FAILED,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/admin/board/tasks/t1/force-fail", json={"reason": "x"}
        )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_force_fail_503_when_board_service_not_configured():
    app = FastAPI()
    app.include_router(
        init_admin_router(
            config_loader=MagicMock(),
            skill_registry=MagicMock(),
            board_service=None,
        )
    )
    from gclaw.auth.dependencies import get_current_user_id
    app.dependency_overrides[get_current_user_id] = lambda: "test_user"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/admin/board/tasks/t1/force-fail", json={"reason": "x"}
        )
    assert resp.status_code == 503
