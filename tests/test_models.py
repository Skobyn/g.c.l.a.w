"""Tests for board task models."""

import pytest
from datetime import datetime, timezone
from gclaw.models.task import (
    BoardTask,
    TaskStatus,
    TaskPriority,
    TaskSource,
    TaskSourceType,
    CronConfig,
    CronMode,
    TaskResult,
    Attachment,
)


def test_create_minimal_task():
    task = BoardTask(
        title="Test task",
        assignee="workspace-mgr",
    )
    assert task.title == "Test task"
    assert task.assignee == "workspace-mgr"
    assert task.status == TaskStatus.BACKLOG
    assert task.priority == TaskPriority.MEDIUM
    assert task.source == TaskSource(type=TaskSourceType.USER)
    assert task.id is not None
    assert task.created_at is not None


def test_create_full_task():
    task = BoardTask(
        title="Schedule meeting",
        description="Book 30min with Sarah",
        status=TaskStatus.QUEUED,
        priority=TaskPriority.HIGH,
        source=TaskSource(type=TaskSourceType.AGENT, origin="research-mgr"),
        assignee="workspace-mgr",
        dependencies=["task_xyz"],
        attachments=[Attachment(type="artifact", ref="artifacts/agenda.md")],
        requires_approval=True,
        cron=CronConfig(schedule="0 8 * * MON", mode=CronMode.AUTO),
    )
    assert task.status == TaskStatus.QUEUED
    assert task.source.origin == "research-mgr"
    assert task.cron.mode == CronMode.AUTO
    assert len(task.attachments) == 1


def test_task_to_firestore_dict():
    task = BoardTask(title="Test", assignee="dev-mgr")
    d = task.to_firestore_dict()
    assert d["title"] == "Test"
    assert d["assignee"] == "dev-mgr"
    assert "id" not in d  # id is the doc key, not a field


def test_task_from_firestore_dict():
    now = datetime.now(timezone.utc)
    d = {
        "title": "From Firestore",
        "description": "",
        "status": "queued",
        "priority": "high",
        "source": {"type": "cron", "origin": "morning-briefing"},
        "assignee": "workspace-mgr",
        "dependencies": [],
        "attachments": [],
        "requires_approval": False,
        "cron": None,
        "result": None,
        "created_at": now,
        "updated_at": now,
    }
    task = BoardTask.from_firestore_dict("task_123", d)
    assert task.id == "task_123"
    assert task.status == TaskStatus.QUEUED
    assert task.source.type == TaskSourceType.CRON


def test_task_complete():
    task = BoardTask(title="Test", assignee="dev-mgr", status=TaskStatus.IN_PROGRESS)
    completed = task.complete(
        TaskResult(summary="Done", artifacts=["out.txt"])
    )
    assert completed.status == TaskStatus.DONE
    assert completed.result.summary == "Done"


def test_invalid_status_transition():
    task = BoardTask(title="Test", assignee="dev-mgr", status=TaskStatus.DONE)
    with pytest.raises(ValueError, match="Cannot transition"):
        task.transition_to(TaskStatus.BACKLOG)
