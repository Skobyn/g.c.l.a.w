"""Tests for CronEventQueueRepo — enqueue / list_pending / mark_drained."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from gclaw.firestore.cron_event_queue_repo import CronEventQueueRepo


@pytest.fixture
def mock_db():
    db = MagicMock()
    # Build collection chain: db.collection("users").document(uid).collection("cron_event_queue")
    return db


@pytest.fixture
def repo(mock_db):
    return CronEventQueueRepo(db=mock_db, user_id="user_123")


def _collection(repo):
    """Shortcut to the mocked inner collection."""
    return (
        repo._db.collection.return_value
        .document.return_value
        .collection.return_value
    )


def test_enqueue_writes_doc_and_returns_id(repo):
    col = _collection(repo)
    new_ref = MagicMock()
    new_ref.id = "evt_abc"
    col.document.return_value = new_ref

    doc_id = repo.enqueue(assignee="orchestrator", text="wake up", cron_id="cron_1")

    assert doc_id == "evt_abc"
    new_ref.set.assert_called_once()
    payload = new_ref.set.call_args[0][0]
    assert payload["assignee"] == "orchestrator"
    assert payload["text"] == "wake up"
    assert payload["cron_id"] == "cron_1"
    assert "queued_at" in payload


def test_list_pending_filters_by_assignee_and_drained(repo):
    col = _collection(repo)

    snap1 = MagicMock()
    snap1.id = "evt_1"
    snap1.to_dict.return_value = {
        "assignee": "orchestrator",
        "text": "hello",
    }
    snap2 = MagicMock()
    snap2.id = "evt_2"
    snap2.to_dict.return_value = {
        "assignee": "orchestrator",
        "text": "old",
        "drained": True,
    }
    query = MagicMock()
    query.stream.return_value = [snap1, snap2]
    col.where.return_value = query

    out = repo.list_pending("orchestrator")

    col.where.assert_called_with("assignee", "==", "orchestrator")
    assert len(out) == 1
    assert out[0]["id"] == "evt_1"
    assert out[0]["text"] == "hello"


def test_mark_drained_deletes_each_doc(repo):
    col = _collection(repo)
    doc_refs = {
        "evt_1": MagicMock(),
        "evt_2": MagicMock(),
    }
    col.document.side_effect = lambda doc_id: doc_refs[doc_id]

    repo.mark_drained(["evt_1", "evt_2"])

    doc_refs["evt_1"].delete.assert_called_once()
    doc_refs["evt_2"].delete.assert_called_once()


def test_mark_drained_noop_on_empty(repo):
    col = _collection(repo)
    repo.mark_drained([])
    col.document.assert_not_called()


def test_mark_drained_swallows_per_doc_errors(repo):
    col = _collection(repo)
    bad = MagicMock()
    bad.delete.side_effect = RuntimeError("gone")
    good = MagicMock()
    col.document.side_effect = lambda doc_id: bad if doc_id == "evt_1" else good

    # Should not raise.
    repo.mark_drained(["evt_1", "evt_2"])
    good.delete.assert_called_once()
