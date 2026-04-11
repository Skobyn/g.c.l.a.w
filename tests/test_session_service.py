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
    session_repo.create.side_effect = lambda s, user_id=None: s

    session = service.create(user_id="user_123", agent_id="orchestrator")

    assert session.user_id == "user_123"
    assert session.agent_id == "orchestrator"
    assert session.status == SessionStatus.ACTIVE
    session_repo.create.assert_called_once()


def test_create_with_id_preserves_supplied_id(service, session_repo):
    session_repo.create.side_effect = lambda s, user_id=None: s

    session = service.create_with_id(
        session_id="sess_custom_abc",
        user_id="user_123",
    )

    assert session.id == "sess_custom_abc"
    assert session.user_id == "user_123"
    assert session.status == SessionStatus.ACTIVE


def test_get_or_none_returns_session(service, session_repo):
    fake = Session(id="sess_1", user_id="user_123")
    session_repo.get.return_value = fake

    result = service.get_or_none("sess_1")
    assert result is fake
    session_repo.get.assert_called_once_with("sess_1", user_id=None)


def test_get_or_none_returns_none_for_missing(service, session_repo):
    session_repo.get.return_value = None
    assert service.get_or_none("nope") is None


def test_append_user_message(service, session_repo):
    existing = Session(id="sess_1", user_id="user_123")
    session_repo.get.return_value = existing
    session_repo.update.side_effect = lambda s, user_id=None: s

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
    session_repo.update.side_effect = lambda s, user_id=None: s

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
    session_repo.update.side_effect = lambda s, user_id=None: s

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
    session_repo.update.side_effect = lambda s, user_id=None: s

    ended = await service.end_session("sess_1")

    assert ended.status == SessionStatus.ENDED
    memory_service.generate_memories.assert_awaited_once()
    session_repo.update.assert_called_once()


@pytest.mark.asyncio
async def test_end_session_without_memory(service_no_memory, session_repo):
    session = Session(id="sess_1", user_id="user_123")
    session_repo.get.return_value = session
    session_repo.update.side_effect = lambda s, user_id=None: s

    ended = await service_no_memory.end_session("sess_1")

    assert ended.status == SessionStatus.ENDED


# ---------------------------------------------------------------------------
# user_id threading (Item A)
# ---------------------------------------------------------------------------


def test_set_active_user_routes_repo_calls(session_repo):
    """SessionService.set_active_user pre-stages user_id for the next
    call; methods called without an explicit user_id kwarg forward the
    active user to the repo."""
    session_repo.create.side_effect = lambda s, user_id=None: s

    svc = SessionService(session_repo=session_repo, memory_service=None)
    svc.set_active_user("auth_user_42")

    svc.create(user_id="auth_user_42")

    session_repo.create.assert_called_once()
    kwargs = session_repo.create.call_args.kwargs
    assert kwargs["user_id"] == "auth_user_42"


def test_explicit_user_id_wins_over_active_user(session_repo):
    session_repo.get.return_value = None

    svc = SessionService(session_repo=session_repo, memory_service=None)
    svc.set_active_user("active_user")

    svc.get_or_none("sess_1", user_id="explicit_user")

    kwargs = session_repo.get.call_args.kwargs
    assert kwargs["user_id"] == "explicit_user"


def test_init_default_user_id_fallback(session_repo):
    """When neither active nor explicit user_id is set, the init default
    is used — this is the dev-mode path."""
    session_repo.get.return_value = None

    svc = SessionService(
        session_repo=session_repo,
        memory_service=None,
        user_id="dev_default_user",
    )

    svc.get_or_none("sess_1")

    kwargs = session_repo.get.call_args.kwargs
    assert kwargs["user_id"] == "dev_default_user"


def test_uid_priority_explicit_then_active_then_default(session_repo):
    """Verify the full _uid priority chain:
    explicit > active > default."""
    session_repo.get.return_value = None
    svc = SessionService(
        session_repo=session_repo,
        memory_service=None,
        user_id="default_u",
    )
    svc.set_active_user("active_u")

    svc.get_or_none("s1")
    assert session_repo.get.call_args.kwargs["user_id"] == "active_u"

    svc.get_or_none("s2", user_id="explicit_u")
    assert session_repo.get.call_args.kwargs["user_id"] == "explicit_u"


def test_append_message_threads_user_id_to_get_and_update(session_repo):
    existing = Session(id="sess_1", user_id="auth_user_42")
    session_repo.get.return_value = existing
    session_repo.update.side_effect = lambda s, user_id=None: s

    svc = SessionService(session_repo=session_repo, memory_service=None)
    svc.append_message("sess_1", "user", "hi", user_id="auth_user_42")

    assert session_repo.get.call_args.kwargs["user_id"] == "auth_user_42"
    assert session_repo.update.call_args.kwargs["user_id"] == "auth_user_42"
