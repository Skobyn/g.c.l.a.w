"""Tests for session model."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from gclaw.models.session import (
    Session,
    SessionMessage,
    SessionStatus,
    MessageRole,
)


def test_create_minimal_session():
    session = Session(user_id="user_123")
    assert session.user_id == "user_123"
    assert session.status == SessionStatus.ACTIVE
    assert session.id.startswith("sess_")
    assert session.messages == []
    assert session.created_at is not None


def test_create_session_with_agent():
    session = Session(
        user_id="user_123",
        agent_id="orchestrator",
        metadata={"source": "chat"},
    )
    assert session.agent_id == "orchestrator"
    assert session.metadata["source"] == "chat"


def test_append_message():
    session = Session(user_id="user_123")
    msg = SessionMessage(role=MessageRole.USER, content="Hello")
    updated = session.append_message(msg)
    assert len(updated.messages) == 1
    assert updated.messages[0].content == "Hello"
    assert updated.messages[0].role == MessageRole.USER
    assert updated.messages[0].timestamp is not None
    # Original is unchanged (immutable copy)
    assert len(session.messages) == 0


def test_append_multiple_messages():
    session = Session(user_id="user_123")
    msg1 = SessionMessage(role=MessageRole.USER, content="Hello")
    msg2 = SessionMessage(role=MessageRole.AGENT, content="Hi there!")
    updated = session.append_message(msg1).append_message(msg2)
    assert len(updated.messages) == 2
    assert updated.messages[0].role == MessageRole.USER
    assert updated.messages[1].role == MessageRole.AGENT


def test_get_recent_messages():
    session = Session(user_id="user_123")
    for i in range(10):
        role = MessageRole.USER if i % 2 == 0 else MessageRole.AGENT
        msg = SessionMessage(role=role, content=f"Message {i}")
        session = session.append_message(msg)

    recent = session.get_recent_messages(limit=3)
    assert len(recent) == 3
    assert recent[0].content == "Message 7"
    assert recent[2].content == "Message 9"


def test_mark_compacted():
    session = Session(user_id="user_123")
    compacted = session.mark_compacted(summary="Session summary here")
    assert compacted.status == SessionStatus.COMPACTED
    assert compacted.compaction_summary == "Session summary here"
    assert compacted.updated_at >= session.updated_at


def test_end_session():
    session = Session(user_id="user_123")
    ended = session.end()
    assert ended.status == SessionStatus.ENDED


def test_session_to_firestore_dict():
    session = Session(user_id="user_123")
    msg = SessionMessage(role=MessageRole.USER, content="Hello")
    session = session.append_message(msg)
    d = session.to_firestore_dict()
    assert d["user_id"] == "user_123"
    assert len(d["messages"]) == 1
    assert d["messages"][0]["content"] == "Hello"
    assert "id" not in d


def test_session_from_firestore_dict():
    now = datetime.now(timezone.utc)
    d = {
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
    session = Session.from_firestore_dict("sess_abc", d)
    assert session.id == "sess_abc"
    assert session.user_id == "user_123"
    assert len(session.messages) == 1
    assert session.messages[0].role == MessageRole.USER


def test_message_count():
    session = Session(user_id="user_123")
    assert session.message_count == 0
    msg = SessionMessage(role=MessageRole.USER, content="Hello")
    session = session.append_message(msg)
    assert session.message_count == 1
