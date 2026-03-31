"""Tests for session repository.

Uses a mock Firestore client to test CRUD without a real database.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone

from gclaw.models.session import (
    Session,
    SessionMessage,
    SessionStatus,
    MessageRole,
)
from gclaw.firestore.session_repo import SessionRepo


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def repo(mock_db):
    return SessionRepo(db=mock_db, user_id="user_123")


def test_session_collection_path(repo):
    ref = repo._collection_ref()
    repo._db.collection.assert_called_with("users")


def test_create_session(repo):
    session = Session(user_id="user_123")
    doc_ref = MagicMock()
    repo._db.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref

    result = repo.create(session)

    doc_ref.set.assert_called_once()
    call_data = doc_ref.set.call_args[0][0]
    assert call_data["user_id"] == "user_123"
    assert "id" not in call_data
    assert result.user_id == "user_123"


def test_get_session(repo):
    now = datetime.now(timezone.utc)
    doc_snap = MagicMock()
    doc_snap.exists = True
    doc_snap.id = "sess_abc"
    doc_snap.to_dict.return_value = {
        "user_id": "user_123",
        "agent_id": "orchestrator",
        "status": "active",
        "messages": [
            {
                "role": "user",
                "content": "Hello",
                "timestamp": now.isoformat(),
            }
        ],
        "metadata": {},
        "compaction_summary": None,
        "created_at": now,
        "updated_at": now,
    }
    repo._db.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = doc_snap

    session = repo.get("sess_abc")
    assert session is not None
    assert session.id == "sess_abc"
    assert session.user_id == "user_123"
    assert len(session.messages) == 1


def test_get_nonexistent_session(repo):
    doc_snap = MagicMock()
    doc_snap.exists = False
    repo._db.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = doc_snap

    session = repo.get("sess_nope")
    assert session is None


def test_update_session(repo):
    session = Session(
        id="sess_abc",
        user_id="user_123",
    )
    msg = SessionMessage(role=MessageRole.USER, content="Hello")
    session = session.append_message(msg)

    doc_ref = MagicMock()
    repo._db.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref

    repo.update(session)

    doc_ref.set.assert_called_once()
    call_data = doc_ref.set.call_args[0][0]
    assert len(call_data["messages"]) == 1


def test_delete_session(repo):
    doc_ref = MagicMock()
    repo._db.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref

    repo.delete("sess_abc")

    doc_ref.delete.assert_called_once()


def test_list_active(repo):
    now = datetime.now(timezone.utc)
    doc1 = MagicMock()
    doc1.id = "sess_1"
    doc1.to_dict.return_value = {
        "user_id": "user_123",
        "agent_id": None,
        "status": "active",
        "messages": [],
        "metadata": {},
        "compaction_summary": None,
        "created_at": now,
        "updated_at": now,
    }
    query_mock = MagicMock()
    query_mock.stream.return_value = [doc1]
    repo._db.collection.return_value.document.return_value.collection.return_value.where.return_value = query_mock

    sessions = repo.list_active()
    assert len(sessions) == 1
    assert sessions[0].status == SessionStatus.ACTIVE
