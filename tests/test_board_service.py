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


@pytest.fixture
def repo():
    return MagicMock()


@pytest.fixture
def service(repo):
    return BoardService(repo=repo)


def test_create_task_from_user(service, repo):
    repo.create.side_effect = lambda t: t
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
    repo.create.side_effect = lambda t: t
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
    repo.update.side_effect = lambda t: t

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
    repo.update.side_effect = lambda t: t

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
    repo.update.side_effect = lambda t: t

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
    repo.list_by_assignee.assert_called_with("workspace-mgr", status=TaskStatus.QUEUED)
