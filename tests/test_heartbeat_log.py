"""Tests for heartbeat log model and repository."""

import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone

from gclaw.heartbeat.log import HeartbeatLog, HeartbeatLogRepo


def test_create_heartbeat_log():
    log = HeartbeatLog(
        context_summary="Board: 5 tasks, 1 failed",
        reasoning="Retrying failed task t3",
        actions_taken=["created retry task for t3"],
        tasks_created=["task_abc123"],
    )
    assert log.id.startswith("hb_")
    assert log.context_summary == "Board: 5 tasks, 1 failed"
    assert len(log.actions_taken) == 1
    assert log.timestamp is not None


def test_create_silent_heartbeat_log():
    log = HeartbeatLog(
        context_summary="Board: 0 tasks",
        reasoning="All quiet, nothing to do.",
        actions_taken=[],
    )
    assert log.actions_taken == []
    assert log.tasks_created == []


def test_heartbeat_log_to_firestore():
    log = HeartbeatLog(
        context_summary="Summary",
        reasoning="Reasoning",
        actions_taken=["action1"],
    )
    d = log.to_firestore_dict()
    assert d["context_summary"] == "Summary"
    assert "id" not in d


def test_heartbeat_log_repo_save():
    mock_db = MagicMock()
    repo = HeartbeatLogRepo(db=mock_db, user_id="user_123")

    log = HeartbeatLog(
        context_summary="Summary",
        reasoning="Reasoning",
        actions_taken=[],
    )

    doc_ref = MagicMock()
    mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref

    repo.save(log)

    doc_ref.set.assert_called_once()
    call_data = doc_ref.set.call_args[0][0]
    assert call_data["context_summary"] == "Summary"


def test_heartbeat_log_repo_list_recent():
    mock_db = MagicMock()
    repo = HeartbeatLogRepo(db=mock_db, user_id="user_123")

    doc1 = MagicMock()
    doc1.id = "hb_1"
    doc1.to_dict.return_value = {
        "context_summary": "Summary 1",
        "reasoning": "Reasoning 1",
        "actions_taken": [],
        "tasks_created": [],
        "timestamp": datetime.now(timezone.utc),
    }

    query_mock = MagicMock()
    query_mock.limit.return_value = query_mock
    query_mock.stream.return_value = [doc1]
    repo._db.collection.return_value.document.return_value.collection.return_value.order_by.return_value = query_mock

    logs = repo.list_recent(limit=10)
    assert len(logs) == 1
    assert logs[0].context_summary == "Summary 1"
