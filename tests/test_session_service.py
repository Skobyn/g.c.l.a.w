"""Tests for session service business logic."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock

from gclaw.models.session import (
    Session,
    SessionMessage,
    SessionStatus,
    MessageRole,
)
from gclaw.session.service import SessionService


@pytest.fixture
def session_repo():
    return MagicMock()


@pytest.fixture
def memory_service():
    """Mock memory service for end-of-session compaction."""
    svc = MagicMock()
    svc.generate_memories = AsyncMock(return_value=[])
    return svc


@pytest.fixture
def service(session_repo, memory_service):
    return SessionService(
        session_repo=session_repo,
        memory_service=memory_service,
        compaction_threshold=10,
    )


@pytest.fixture
def service_no_memory(session_repo):
    """Service without memory integration."""
    return SessionService(
        session_repo=session_repo,
        memory_service=None,
        compaction_threshold=10,
    )


def test_create_session(service, session_repo):
    session_repo.create.side_effect = lambda s: s

    session = service.create(user_id="user_123", agent_id="orchestrator")

    assert session.user_id == "user_123"
    assert session.agent_id == "orchestrator"
    assert session.status == SessionStatus.ACTIVE
    session_repo.create.assert_called_once()


def test_append_user_message(service, session_repo):
    existing = Session(id="sess_1", user_id="user_123")
    session_repo.get.return_value = existing
    session_repo.update.side_effect = lambda s: s

    updated = service.append_message(
        session_id="sess_1",
        role="user",
        content="Hello",
    )

    assert len(updated.messages) == 1
    assert updated.messages[0].content == "Hello"
    assert updated.messages[0].role == MessageRole.USER
    session_repo.update.assert_called_once()


def test_append_agent_message(service, session_repo):
    existing = Session(id="sess_1", user_id="user_123")
    session_repo.get.return_value = existing
    session_repo.update.side_effect = lambda s: s

    updated = service.append_message(
        session_id="sess_1",
        role="agent",
        content="Hi there!",
    )

    assert updated.messages[0].role == MessageRole.AGENT


def test_append_to_nonexistent_raises(service, session_repo):
    session_repo.get.return_value = None
    with pytest.raises(ValueError, match="not found"):
        service.append_message("sess_nope", "user", "Hello")


def test_get_history(service, session_repo):
    session = Session(id="sess_1", user_id="user_123")
    for i in range(5):
        role = MessageRole.USER if i % 2 == 0 else MessageRole.AGENT
        msg = SessionMessage(role=role, content=f"Msg {i}")
        session = session.append_message(msg)
    session_repo.get.return_value = session

    history = service.get_history("sess_1", limit=3)

    assert len(history) == 3
    assert history[0].content == "Msg 2"


def test_get_history_all(service, session_repo):
    session = Session(id="sess_1", user_id="user_123")
    for i in range(3):
        msg = SessionMessage(role=MessageRole.USER, content=f"Msg {i}")
        session = session.append_message(msg)
    session_repo.get.return_value = session

    history = service.get_history("sess_1")

    assert len(history) == 3


def test_needs_compaction(service, session_repo):
    session = Session(id="sess_1", user_id="user_123")
    # Below threshold
    for i in range(5):
        msg = SessionMessage(role=MessageRole.USER, content=f"Msg {i}")
        session = session.append_message(msg)

    assert service.needs_compaction(session) is False

    # At threshold
    for i in range(5, 10):
        msg = SessionMessage(role=MessageRole.USER, content=f"Msg {i}")
        session = session.append_message(msg)

    assert service.needs_compaction(session) is True


def test_compact_session(service, session_repo):
    session = Session(id="sess_1", user_id="user_123")
    for i in range(15):
        msg = SessionMessage(role=MessageRole.USER, content=f"Message {i}")
        session = session.append_message(msg)
    session_repo.get.return_value = session
    session_repo.update.side_effect = lambda s: s

    compacted = service.compact(
        session_id="sess_1",
        summary="Summary of first 10 messages",
        keep_recent=5,
    )

    assert compacted.compaction_summary == "Summary of first 10 messages"
    assert len(compacted.messages) == 5
    assert compacted.messages[0].content == "Message 10"
    session_repo.update.assert_called_once()


@pytest.mark.asyncio
async def test_end_session_with_memory(service, session_repo, memory_service):
    session = Session(id="sess_1", user_id="user_123")
    msg = SessionMessage(role=MessageRole.USER, content="Remember I like coffee")
    session = session.append_message(msg)
    session_repo.get.return_value = session
    session_repo.update.side_effect = lambda s: s

    ended = await service.end_session("sess_1")

    assert ended.status == SessionStatus.ENDED
    memory_service.generate_memories.assert_awaited_once()
    session_repo.update.assert_called_once()


@pytest.mark.asyncio
async def test_end_session_without_memory(service_no_memory, session_repo):
    session = Session(id="sess_1", user_id="user_123")
    session_repo.get.return_value = session
    session_repo.update.side_effect = lambda s: s

    ended = await service_no_memory.end_session("sess_1")

    assert ended.status == SessionStatus.ENDED
