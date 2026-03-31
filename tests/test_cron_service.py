"""Tests for cron service business logic."""

import pytest
from unittest.mock import MagicMock

from gclaw.models.cron import Cron, CronMode, CronStatus
from gclaw.models.task import BoardTask, TaskStatus, TaskSourceType
from gclaw.cron.service import CronService


@pytest.fixture
def cron_repo():
    return MagicMock()


@pytest.fixture
def board_service():
    return MagicMock()


@pytest.fixture
def service(cron_repo, board_service):
    return CronService(cron_repo=cron_repo, board_service=board_service)


def test_create_cron(service, cron_repo):
    cron_repo.create.side_effect = lambda c: c
    cron = service.create(
        title="Morning briefing",
        schedule="0 8 * * *",
        assignee="workspace-mgr",
        mode="todo",
        description="Daily morning update",
    )
    assert cron.title == "Morning briefing"
    assert cron.mode == CronMode.TODO
    assert cron.status == CronStatus.ACTIVE
    cron_repo.create.assert_called_once()


def test_update_cron(service, cron_repo):
    existing = Cron(
        id="cron_1",
        title="Old title",
        schedule="0 8 * * *",
        assignee="workspace-mgr",
    )
    cron_repo.get.return_value = existing
    cron_repo.update.side_effect = lambda c: c

    updated = service.update(
        cron_id="cron_1",
        title="New title",
        schedule="0 9 * * *",
    )
    assert updated.title == "New title"
    assert updated.schedule == "0 9 * * *"
    cron_repo.update.assert_called_once()


def test_update_nonexistent_raises(service, cron_repo):
    cron_repo.get.return_value = None
    with pytest.raises(ValueError, match="not found"):
        service.update(cron_id="cron_nope", title="X")


def test_delete_cron(service, cron_repo):
    service.delete("cron_1")
    cron_repo.delete.assert_called_once_with("cron_1")


def test_list_crons(service, cron_repo):
    cron_repo.list_all.return_value = [
        Cron(title="C1", schedule="0 8 * * *", assignee="dev-mgr"),
        Cron(title="C2", schedule="0 9 * * *", assignee="workspace-mgr"),
    ]
    crons = service.list_all()
    assert len(crons) == 2


def test_pause_cron(service, cron_repo):
    cron = Cron(
        id="cron_1",
        title="Active cron",
        schedule="0 8 * * *",
        assignee="workspace-mgr",
        status=CronStatus.ACTIVE,
    )
    cron_repo.get.return_value = cron
    cron_repo.update.side_effect = lambda c: c

    paused = service.pause("cron_1")
    assert paused.status == CronStatus.PAUSED


def test_resume_cron(service, cron_repo):
    cron = Cron(
        id="cron_1",
        title="Paused cron",
        schedule="0 8 * * *",
        assignee="workspace-mgr",
        status=CronStatus.PAUSED,
    )
    cron_repo.get.return_value = cron
    cron_repo.update.side_effect = lambda c: c

    resumed = service.resume("cron_1")
    assert resumed.status == CronStatus.ACTIVE


def test_execute_todo_mode(service, cron_repo, board_service):
    cron = Cron(
        id="cron_1",
        title="Todo cron",
        schedule="0 8 * * *",
        assignee="workspace-mgr",
        mode=CronMode.TODO,
        description="Check emails",
        task_priority="medium",
    )
    cron_repo.get.return_value = cron
    cron_repo.update.side_effect = lambda c: c
    board_service.create_task.side_effect = lambda **kw: BoardTask(
        title=kw["title"], assignee=kw["assignee"]
    )

    task = service.execute("cron_1")

    board_service.create_task.assert_called_once()
    call_kwargs = board_service.create_task.call_args.kwargs
    assert call_kwargs["title"] == "Todo cron"
    assert call_kwargs["status"] == TaskStatus.BACKLOG
    assert call_kwargs["source_type"] == "cron"
    assert call_kwargs["source_origin"] == "cron_1"


def test_execute_auto_mode(service, cron_repo, board_service):
    cron = Cron(
        id="cron_2",
        title="Auto cron",
        schedule="*/30 * * * *",
        assignee="workspace-mgr",
        mode=CronMode.AUTO,
        description="Triage inbox",
        task_priority="high",
    )
    cron_repo.get.return_value = cron
    cron_repo.update.side_effect = lambda c: c
    board_service.create_task.side_effect = lambda **kw: BoardTask(
        title=kw["title"], assignee=kw["assignee"], status=TaskStatus(kw.get("status", "backlog"))
    )

    task = service.execute("cron_2")

    call_kwargs = board_service.create_task.call_args.kwargs
    assert call_kwargs["status"] == TaskStatus.QUEUED
    assert call_kwargs["priority"] == "high"


def test_execute_paused_cron_raises(service, cron_repo):
    cron = Cron(
        id="cron_1",
        title="Paused",
        schedule="0 8 * * *",
        assignee="workspace-mgr",
        status=CronStatus.PAUSED,
    )
    cron_repo.get.return_value = cron

    with pytest.raises(ValueError, match="paused"):
        service.execute("cron_1")


def test_execute_nonexistent_raises(service, cron_repo):
    cron_repo.get.return_value = None
    with pytest.raises(ValueError, match="not found"):
        service.execute("cron_nope")
