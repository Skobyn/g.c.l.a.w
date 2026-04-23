"""Tests for BoardService.sweep_stalled + admin endpoint."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from gclaw.api.admin_routes import init_admin_router
from gclaw.board.service import BoardService
from gclaw.models.task import BoardTask, TaskStatus


def _mk(
    tid: str, status: TaskStatus, updated: datetime, assignee: str = "research-mgr"
) -> BoardTask:
    return BoardTask(
        id=tid,
        title="t",
        assignee=assignee,
        status=status,
        updated_at=updated,
    )


@pytest.fixture
def repo():
    return MagicMock()


@pytest.fixture
def service(repo):
    return BoardService(repo=repo, user_id="u")


# ── service-layer ──────────────────────────────────────────────────


def test_sweep_stalled_fails_only_old_in_progress(service, repo):
    now = datetime.now(timezone.utc)
    old = _mk("old", TaskStatus.IN_PROGRESS, now - timedelta(minutes=30))
    fresh = _mk("fresh", TaskStatus.IN_PROGRESS, now - timedelta(minutes=2))
    queued_old = _mk("queued", TaskStatus.QUEUED, now - timedelta(hours=2))
    done_old = _mk("done", TaskStatus.DONE, now - timedelta(hours=2))
    repo.list_all.return_value = [old, fresh, queued_old, done_old]
    # fail() needs get() + update() — wire through on the mock.
    repo.get.side_effect = lambda tid, user_id=None: {
        "old": old, "fresh": fresh, "queued": queued_old, "done": done_old,
    }[tid]
    repo.update.side_effect = lambda t, user_id=None: t

    failed = service.sweep_stalled(max_age_seconds=900)  # 15min

    assert failed == ["old"]


def test_sweep_stalled_respects_custom_threshold(service, repo):
    now = datetime.now(timezone.utc)
    t = _mk("t1", TaskStatus.IN_PROGRESS, now - timedelta(minutes=10))
    repo.list_all.return_value = [t]
    repo.get.return_value = t
    repo.update.side_effect = lambda task, user_id=None: task

    # At 15min threshold, 10min-old task is fresh.
    assert service.sweep_stalled(max_age_seconds=15 * 60) == []
    # At 5min threshold, it's stale.
    assert service.sweep_stalled(max_age_seconds=5 * 60) == ["t1"]


def test_sweep_stalled_handles_naive_updated_at(service, repo):
    """Firestore sometimes returns naive datetimes; treat as UTC."""
    naive_old = datetime.utcnow() - timedelta(minutes=30)  # no tzinfo
    t = _mk("t1", TaskStatus.IN_PROGRESS, naive_old)
    repo.list_all.return_value = [t]
    repo.get.return_value = t
    repo.update.side_effect = lambda task, user_id=None: task

    failed = service.sweep_stalled(max_age_seconds=900)
    assert failed == ["t1"]


def test_sweep_stalled_continues_after_per_row_error(service, repo):
    now = datetime.now(timezone.utc)
    a = _mk("a", TaskStatus.IN_PROGRESS, now - timedelta(minutes=30))
    b = _mk("b", TaskStatus.IN_PROGRESS, now - timedelta(minutes=30))
    repo.list_all.return_value = [a, b]
    # First fail raises, second succeeds.
    repo.get.side_effect = [ValueError("boom"), b, b]
    repo.update.side_effect = lambda task, user_id=None: task

    failed = service.sweep_stalled(max_age_seconds=900)
    # b still got swept; a was skipped but didn't abort the loop.
    assert "b" in failed
    assert "a" not in failed


# ── admin endpoint ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_sweep_endpoint_returns_failed_ids():
    board = MagicMock()
    board.sweep_stalled.return_value = ["t1", "t2"]

    app = FastAPI()
    app.include_router(
        init_admin_router(
            config_loader=MagicMock(),
            skill_registry=MagicMock(),
            board_service=board,
        )
    )
    from gclaw.auth.dependencies import get_current_user_id
    app.dependency_overrides[get_current_user_id] = lambda: "u"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.post(
            "/admin/board/tasks/sweep-stalled",
            json={"max_age_seconds": 600},
        )
    assert resp.status_code == 200
    assert resp.json() == {
        "status": "ok",
        "failed_count": 2,
        "failed_ids": ["t1", "t2"],
    }
    board.sweep_stalled.assert_called_once_with(
        max_age_seconds=600, user_id="u"
    )


@pytest.mark.asyncio
async def test_admin_sweep_endpoint_defaults_to_15min():
    board = MagicMock()
    board.sweep_stalled.return_value = []

    app = FastAPI()
    app.include_router(
        init_admin_router(
            config_loader=MagicMock(),
            skill_registry=MagicMock(),
            board_service=board,
        )
    )
    from gclaw.auth.dependencies import get_current_user_id
    app.dependency_overrides[get_current_user_id] = lambda: "u"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.post("/admin/board/tasks/sweep-stalled", json={})
    assert resp.status_code == 200
    board.sweep_stalled.assert_called_once_with(
        max_age_seconds=900, user_id="u"
    )
