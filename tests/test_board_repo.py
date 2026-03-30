"""Tests for board repository.

Uses a mock Firestore client to test CRUD without a real database.
"""

import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone

from gclaw.models.task import BoardTask, TaskStatus
from gclaw.firestore.board_repo import BoardRepo


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def repo(mock_db):
    return BoardRepo(db=mock_db, user_id="user_123")


def test_task_collection_path(repo):
    ref = repo._collection_ref()
    repo._db.collection.assert_called_with("users")


def test_create_task(repo):
    task = BoardTask(title="Test task", assignee="workspace-mgr")
    doc_ref = MagicMock()
    repo._db.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref

    repo.create(task)

    doc_ref.set.assert_called_once()
    call_data = doc_ref.set.call_args[0][0]
    assert call_data["title"] == "Test task"
    assert "id" not in call_data


def test_get_task(repo):
    doc_snap = MagicMock()
    doc_snap.exists = True
    doc_snap.id = "task_abc"
    doc_snap.to_dict.return_value = {
        "title": "Found task",
        "description": "",
        "status": "queued",
        "priority": "medium",
        "source": {"type": "user", "origin": None},
        "assignee": "dev-mgr",
        "dependencies": [],
        "attachments": [],
        "requires_approval": False,
        "cron": None,
        "result": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    repo._db.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = doc_snap

    task = repo.get("task_abc")
    assert task is not None
    assert task.title == "Found task"
    assert task.id == "task_abc"


def test_get_nonexistent_task(repo):
    doc_snap = MagicMock()
    doc_snap.exists = False
    repo._db.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = doc_snap

    task = repo.get("task_nope")
    assert task is None


def test_update_task(repo):
    task = BoardTask(
        id="task_abc",
        title="Updated",
        assignee="dev-mgr",
        status=TaskStatus.IN_PROGRESS,
    )
    doc_ref = MagicMock()
    repo._db.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref

    repo.update(task)

    doc_ref.set.assert_called_once()
    call_data = doc_ref.set.call_args[0][0]
    assert call_data["status"] == "in_progress"


def test_list_by_status(repo):
    doc1 = MagicMock()
    doc1.id = "task_1"
    doc1.to_dict.return_value = {
        "title": "Task 1",
        "description": "",
        "status": "queued",
        "priority": "medium",
        "source": {"type": "user", "origin": None},
        "assignee": "workspace-mgr",
        "dependencies": [],
        "attachments": [],
        "requires_approval": False,
        "cron": None,
        "result": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    query_mock = MagicMock()
    query_mock.stream.return_value = [doc1]
    repo._db.collection.return_value.document.return_value.collection.return_value.where.return_value = query_mock

    tasks = repo.list_by_status(TaskStatus.QUEUED)
    assert len(tasks) == 1
    assert tasks[0].title == "Task 1"


def test_list_by_assignee(repo):
    doc1 = MagicMock()
    doc1.id = "task_1"
    doc1.to_dict.return_value = {
        "title": "My Task",
        "description": "",
        "status": "queued",
        "priority": "high",
        "source": {"type": "agent", "origin": "orchestrator"},
        "assignee": "workspace-mgr",
        "dependencies": [],
        "attachments": [],
        "requires_approval": False,
        "cron": None,
        "result": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    query_mock = MagicMock()
    query_mock.stream.return_value = [doc1]
    base_query = MagicMock()
    base_query.where.return_value = query_mock
    repo._db.collection.return_value.document.return_value.collection.return_value.where.return_value = base_query

    tasks = repo.list_by_assignee("workspace-mgr")
    assert len(tasks) == 1
    assert tasks[0].assignee == "workspace-mgr"
