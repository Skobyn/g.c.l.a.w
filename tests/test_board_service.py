"""Tests for board service business logic."""

import pytest
from unittest.mock import MagicMock

from gclaw.models.task import (
    BoardTask,
    TaskStatus,
    TaskSource,
    TaskSourceType,
    TaskResult,
)
from gclaw.board.service import BoardService
from gclaw.board.transitions import TransitionNotAllowed


@pytest.fixture
def repo():
    return MagicMock()


@pytest.fixture
def service(repo):
    return BoardService(repo=repo)


def test_create_task_from_user(service, repo):
    repo.create.side_effect = lambda t, user_id=None: t
    task = service.create_task(
        title="Do the thing",
        assignee="workspace-mgr",
        source_type="user",
    )
    assert task.title == "Do the thing"
    assert task.source.type == TaskSourceType.USER
    assert task.status == TaskStatus.BACKLOG
    repo.create.assert_called_once()


def test_create_task_from_agent(service, repo):
    repo.create.side_effect = lambda t, user_id=None: t
    task = service.create_task(
        title="Subtask",
        assignee="workspace-mgr",
        source_type="agent",
        source_origin="research-mgr",
        status=TaskStatus.QUEUED,
    )
    assert task.source.type == TaskSourceType.AGENT
    assert task.source.origin == "research-mgr"
    assert task.status == TaskStatus.QUEUED


def test_pick_up_task(service, repo):
    task = BoardTask(
        id="task_1",
        title="Queued task",
        assignee="workspace-mgr",
        status=TaskStatus.QUEUED,
    )
    repo.get.return_value = task
    repo.update.side_effect = lambda t, user_id=None: t

    picked = service.pick_up("task_1")
    assert picked.status == TaskStatus.IN_PROGRESS
    repo.update.assert_called_once()


def test_pick_up_nonexistent_raises(service, repo):
    repo.get.return_value = None
    with pytest.raises(ValueError, match="not found"):
        service.pick_up("nope")


def test_complete_task(service, repo):
    task = BoardTask(
        id="task_1",
        title="In progress task",
        assignee="dev-mgr",
        status=TaskStatus.IN_PROGRESS,
    )
    repo.get.return_value = task
    repo.update.side_effect = lambda t, user_id=None: t

    completed = service.complete(
        "task_1", summary="All done", artifacts=["out.txt"]
    )
    assert completed.status == TaskStatus.DONE
    assert completed.result.summary == "All done"


def test_fail_task(service, repo):
    task = BoardTask(
        id="task_1",
        title="Failing task",
        assignee="dev-mgr",
        status=TaskStatus.IN_PROGRESS,
    )
    repo.get.return_value = task
    repo.update.side_effect = lambda t, user_id=None: t

    failed = service.fail("task_1", reason="API timeout")
    assert failed.status == TaskStatus.FAILED
    assert failed.result.summary == "API timeout"


def test_get_pending_tasks_for_agent(service, repo):
    tasks = [
        BoardTask(id="t1", title="T1", assignee="workspace-mgr", status=TaskStatus.QUEUED),
    ]
    repo.list_by_assignee.return_value = tasks

    result = service.get_pending_tasks("workspace-mgr")
    assert len(result) == 1
    repo.list_by_assignee.assert_called_with(
        "workspace-mgr", status=TaskStatus.QUEUED, user_id=None
    )


def test_move_status_allowed(service, repo):
    task = BoardTask(
        id="t1",
        title="T",
        assignee="workspace-mgr",
        status=TaskStatus.BACKLOG,
    )
    repo.get.return_value = task
    repo.update.side_effect = lambda t, user_id=None: t

    moved = service.move_status("t1", TaskStatus.QUEUED, user_id="u1")
    assert moved.status == TaskStatus.QUEUED


def test_move_status_forbidden_raises(service, repo):
    task = BoardTask(
        id="t1",
        title="T",
        assignee="workspace-mgr",
        status=TaskStatus.BACKLOG,
    )
    repo.get.return_value = task

    with pytest.raises(TransitionNotAllowed):
        service.move_status("t1", TaskStatus.DONE, user_id="u1")
    repo.update.assert_not_called()


def test_move_status_missing_task_raises(service, repo):
    repo.get.return_value = None
    with pytest.raises(ValueError, match="not found"):
        service.move_status("nope", TaskStatus.QUEUED, user_id="u1")


def test_approve_happy_path(service, repo):
    task = BoardTask(
        id="t1",
        title="T",
        assignee="workspace-mgr",
        status=TaskStatus.NEEDS_APPROVAL,
    )
    repo.get.return_value = task
    repo.update.side_effect = lambda t, user_id=None: t

    approved = service.approve("t1", user_id="u1", note="go ahead")
    assert approved.status == TaskStatus.QUEUED
    assert approved.approved_by == "u1"
    assert approved.approved_at is not None
    assert approved.approval_note == "go ahead"


def test_approve_wrong_status_raises(service, repo):
    task = BoardTask(
        id="t1",
        title="T",
        assignee="workspace-mgr",
        status=TaskStatus.QUEUED,
    )
    repo.get.return_value = task

    with pytest.raises(ValueError, match="not awaiting approval"):
        service.approve("t1", user_id="u1")


def test_reject_happy_path(service, repo):
    task = BoardTask(
        id="t1",
        title="T",
        assignee="workspace-mgr",
        status=TaskStatus.NEEDS_APPROVAL,
    )
    repo.get.return_value = task
    repo.update.side_effect = lambda t, user_id=None: t

    rejected = service.reject("t1", user_id="u1", note="bad idea")
    assert rejected.status == TaskStatus.FAILED
    assert rejected.rejection_note == "bad idea"
    assert rejected.rejected_at is not None


def test_reject_wrong_status_raises(service, repo):
    task = BoardTask(
        id="t1",
        title="T",
        assignee="workspace-mgr",
        status=TaskStatus.DONE,
    )
    repo.get.return_value = task

    with pytest.raises(ValueError, match="not awaiting approval"):
        service.reject("t1", user_id="u1", note="no")
