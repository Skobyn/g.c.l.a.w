"""Tests for cron repository.

Uses a mock Firestore client to test CRUD without a real database.
"""

import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone

from gclaw.models.cron import (
    AgentTurnPayload,
    Cron,
    CronExprSchedule,
    CronMode,
    CronStatus,
)
from gclaw.firestore.cron_repo import CronRepo


def _cron(**kw):
    base = dict(
        title="Morning briefing",
        assignee="workspace-mgr",
        schedule=CronExprSchedule(expr="0 8 * * *"),
        payload=AgentTurnPayload(message="do"),
    )
    base.update(kw)
    return Cron(**base)


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def repo(mock_db):
    return CronRepo(db=mock_db, user_id="user_123")


def test_cron_collection_path(repo):
    ref = repo._collection_ref()
    repo._db.collection.assert_called_with("users")


def test_create_cron(repo):
    cron = _cron()
    doc_ref = MagicMock()
    repo._db.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref

    result = repo.create(cron)

    doc_ref.set.assert_called_once()
    call_data = doc_ref.set.call_args[0][0]
    assert call_data["title"] == "Morning briefing"
    assert "id" not in call_data
    assert result.title == "Morning briefing"


def test_get_cron(repo):
    doc_snap = MagicMock()
    doc_snap.exists = True
    doc_snap.id = "cron_abc"
    doc_snap.to_dict.return_value = {
        "title": "Found cron",
        "description": "",
        "schedule": "0 9 * * *",
        "mode": "auto",
        "status": "active",
        "assignee": "dev-mgr",
        "task_priority": "medium",
        "last_run": None,
        "next_run": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    repo._db.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = doc_snap

    cron = repo.get("cron_abc")
    assert cron is not None
    assert cron.title == "Found cron"
    assert cron.id == "cron_abc"
    assert cron.mode == CronMode.AUTO


def test_get_nonexistent_cron(repo):
    doc_snap = MagicMock()
    doc_snap.exists = False
    repo._db.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = doc_snap

    cron = repo.get("cron_nope")
    assert cron is None


def test_update_cron(repo):
    cron = _cron(
        id="cron_abc",
        title="Updated cron",
        schedule=CronExprSchedule(expr="0 10 * * *"),
        assignee="dev-mgr",
    )
    doc_ref = MagicMock()
    repo._db.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref

    repo.update(cron)

    doc_ref.set.assert_called_once()
    call_data = doc_ref.set.call_args[0][0]
    assert call_data["schedule"] == {"kind": "cron", "expr": "0 10 * * *", "tz": None, "stagger_ms": None}


def test_delete_cron(repo):
    doc_ref = MagicMock()
    repo._db.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref

    repo.delete("cron_abc")

    doc_ref.delete.assert_called_once()


def test_list_all(repo):
    doc1 = MagicMock()
    doc1.id = "cron_1"
    doc1.to_dict.return_value = {
        "title": "Cron 1",
        "description": "",
        "schedule": "0 8 * * *",
        "mode": "todo",
        "status": "active",
        "assignee": "workspace-mgr",
        "task_priority": "medium",
        "last_run": None,
        "next_run": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    doc2 = MagicMock()
    doc2.id = "cron_2"
    doc2.to_dict.return_value = {
        "title": "Cron 2",
        "description": "",
        "schedule": "0 17 * * FRI",
        "mode": "auto",
        "status": "paused",
        "assignee": "research-mgr",
        "task_priority": "low",
        "last_run": None,
        "next_run": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    repo._db.collection.return_value.document.return_value.collection.return_value.stream.return_value = [doc1, doc2]

    crons = repo.list_all()
    assert len(crons) == 2
    assert crons[0].title == "Cron 1"
    assert crons[1].title == "Cron 2"


def test_list_active(repo):
    doc1 = MagicMock()
    doc1.id = "cron_1"
    doc1.to_dict.return_value = {
        "title": "Active cron",
        "description": "",
        "schedule": "0 8 * * *",
        "mode": "todo",
        "status": "active",
        "assignee": "workspace-mgr",
        "task_priority": "medium",
        "last_run": None,
        "next_run": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    query_mock = MagicMock()
    query_mock.stream.return_value = [doc1]
    repo._db.collection.return_value.document.return_value.collection.return_value.where.return_value = query_mock

    crons = repo.list_active()
    assert len(crons) == 1
    assert crons[0].status == CronStatus.ACTIVE
