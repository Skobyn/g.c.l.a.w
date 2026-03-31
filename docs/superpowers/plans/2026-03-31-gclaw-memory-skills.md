# GClaw Vertex AI Memory Bank, Session Management & Skill System (Plan 3 of 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the memory layer (Vertex AI Memory Bank REST API client + session management with compaction), the skill system (model, registry, loader, discovery), and integrate both into the existing agent infrastructure (AgentRunner hooks for auto-recall/auto-capture, heartbeat context enrichment with memories).

**Architecture:** The Memory Bank client wraps Google's Vertex AI Memory Bank REST API using `httpx` for HTTP and `google.auth` for credentials. Sessions are Firestore documents containing message history with compaction support. Skills are file-based definitions (skill.json + instructions.md + examples.md) loaded into a Firestore-backed registry with semantic discovery. All three systems integrate into the existing AgentRunner, HeartbeatContextGatherer, and ConfigLoader from Plans 1-2.

**Tech Stack:** Python 3.10, google-adk, FastAPI, google-cloud-firestore, httpx, google-auth, Pydantic, pytest, Docker, Cloud Run

**Builds on Plans 1-2:**
- `BoardService` / `BoardRepo` for task board operations
- `AgentFactory` / `AgentRunner` for agent execution
- `HeartbeatContextGatherer` / `HeartbeatService` for consciousness loop
- `ConfigLoader` for system prompt assembly
- `create_app` for API endpoints
- `Settings` for configuration

**Subsequent Plans:**
- Plan 4: Next.js web app + voice + auth + multi-user A2A

---

## File Structure

```
gclaw/
├── src/
│   └── gclaw/
│       ├── settings.py                    # MODIFY: add memory bank + skill config
│       ├── config/
│       │   └── loader.py                  # MODIFY: merge skill instructions into prompts
│       ├── models/
│       │   ├── session.py                 # NEW: Session Pydantic model
│       │   ├── memory.py                  # NEW: Memory Pydantic models
│       │   └── skill.py                   # NEW: Skill Pydantic model
│       ├── firestore/
│       │   ├── session_repo.py            # NEW: Session Firestore CRUD
│       │   └── skill_repo.py             # NEW: Skill registry Firestore CRUD
│       ├── session/
│       │   ├── __init__.py
│       │   └── service.py                # NEW: Session business logic + compaction
│       ├── memory/
│       │   ├── __init__.py
│       │   ├── client.py                 # NEW: Vertex AI Memory Bank REST client
│       │   └── service.py               # NEW: Memory service (recall, capture, scoping)
│       ├── skill/
│       │   ├── __init__.py
│       │   ├── registry.py              # NEW: Skill registry (load + Firestore)
│       │   ├── loader.py                # NEW: Skill file loader (skill.json + *.md)
│       │   └── discovery.py             # NEW: Skill discovery by context
│       ├── heartbeat/
│       │   └── context.py               # MODIFY: include memories in context
│       ├── dispatch/
│       │   └── runner.py                # MODIFY: add memory hooks (auto-recall/capture)
│       └── api/
│           └── app.py                   # MODIFY: accept new services
├── tests/
│   ├── test_session_model.py            # NEW
│   ├── test_session_repo.py             # NEW
│   ├── test_session_service.py          # NEW
│   ├── test_memory_client.py            # NEW
│   ├── test_memory_service.py           # NEW
│   ├── test_skill_model.py              # NEW
│   ├── test_skill_registry.py           # NEW
│   ├── test_skill_loader.py             # NEW
│   ├── test_skill_discovery.py          # NEW
│   ├── test_runner_memory.py            # NEW
│   └── test_heartbeat_memory.py         # NEW
└── skills/
    └── email-drafter/                    # NEW: Example built-in skill
        ├── skill.json
        ├── instructions.md
        └── examples.md
```

---

### Task 1: Session Model (Pydantic)

**Files:**
- Create: `src/gclaw/models/session.py`
- Create: `tests/test_session_model.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_session_model.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_session_model.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gclaw.models.session'`

- [ ] **Step 3: Implement session model**

Create `src/gclaw/models/session.py`:

```python
"""Session model for conversation state management."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field
from typing_extensions import Self


class SessionStatus(str, Enum):
    ACTIVE = "active"
    ENDED = "ended"
    COMPACTED = "compacted"


class MessageRole(str, Enum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


class SessionMessage(BaseModel):
    """A single message in a session's history."""

    role: MessageRole
    content: str
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class Session(BaseModel):
    """A conversation session stored in Firestore.

    Contains the message history between the user and agents.
    Sessions can be compacted (summarized) when context fills up,
    with the summary stored and raw messages optionally retained.
    """

    id: str = Field(default_factory=lambda: f"sess_{uuid.uuid4().hex[:12]}")
    user_id: str
    agent_id: str | None = None
    status: SessionStatus = SessionStatus.ACTIVE
    messages: list[SessionMessage] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    compaction_summary: str | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def message_count(self) -> int:
        return len(self.messages)

    def append_message(self, message: SessionMessage) -> Self:
        """Return a copy with the message appended."""
        new_messages = list(self.messages) + [message]
        return self.model_copy(
            update={
                "messages": new_messages,
                "updated_at": datetime.now(timezone.utc),
            }
        )

    def get_recent_messages(self, limit: int = 20) -> list[SessionMessage]:
        """Get the most recent messages."""
        return self.messages[-limit:]

    def mark_compacted(self, summary: str) -> Self:
        """Mark the session as compacted with a summary."""
        return self.model_copy(
            update={
                "status": SessionStatus.COMPACTED,
                "compaction_summary": summary,
                "updated_at": datetime.now(timezone.utc),
            }
        )

    def end(self) -> Self:
        """Mark the session as ended."""
        return self.model_copy(
            update={
                "status": SessionStatus.ENDED,
                "updated_at": datetime.now(timezone.utc),
            }
        )

    def to_firestore_dict(self) -> dict:
        d = self.model_dump(mode="json")
        d.pop("id")
        return d

    @classmethod
    def from_firestore_dict(cls, doc_id: str, data: dict) -> Self:
        return cls(id=doc_id, **data)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_session_model.py -v`
Expected: All 11 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/gclaw/models/session.py tests/test_session_model.py
git commit -m "feat: session Pydantic model with message history and compaction support"
```

---

### Task 2: Session Firestore Repository

**Files:**
- Create: `src/gclaw/firestore/session_repo.py`
- Create: `tests/test_session_repo.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_session_repo.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_session_repo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gclaw.firestore.session_repo'`

- [ ] **Step 3: Implement session repository**

Create `src/gclaw/firestore/session_repo.py`:

```python
"""Session CRUD operations on Firestore.

Collection path: users/{userId}/sessions/{sessionId}
"""

from __future__ import annotations

from google.cloud.firestore import Client as FirestoreClient

from gclaw.models.session import Session, SessionStatus


class SessionRepo:
    """Synchronous Firestore repository for sessions."""

    def __init__(self, db: FirestoreClient, user_id: str) -> None:
        self._db = db
        self._user_id = user_id

    def _collection_ref(self):
        return (
            self._db.collection("users")
            .document(self._user_id)
            .collection("sessions")
        )

    def create(self, session: Session) -> Session:
        doc_ref = self._collection_ref().document(session.id)
        doc_ref.set(session.to_firestore_dict())
        return session

    def get(self, session_id: str) -> Session | None:
        doc = self._collection_ref().document(session_id).get()
        if not doc.exists:
            return None
        return Session.from_firestore_dict(doc.id, doc.to_dict())

    def update(self, session: Session) -> Session:
        doc_ref = self._collection_ref().document(session.id)
        doc_ref.set(session.to_firestore_dict())
        return session

    def delete(self, session_id: str) -> None:
        self._collection_ref().document(session_id).delete()

    def list_active(self) -> list[Session]:
        docs = (
            self._collection_ref()
            .where("status", "==", SessionStatus.ACTIVE.value)
            .stream()
        )
        return [
            Session.from_firestore_dict(doc.id, doc.to_dict()) for doc in docs
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_session_repo.py -v`
Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/gclaw/firestore/session_repo.py tests/test_session_repo.py
git commit -m "feat: Firestore session repository with CRUD and active listing"
```

---

### Task 3: Session Service (Create, Append, Get History, Compact)

**Files:**
- Create: `src/gclaw/session/__init__.py`
- Create: `src/gclaw/session/service.py`
- Create: `tests/test_session_service.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_session_service.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_session_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gclaw.session'`

- [ ] **Step 3: Implement session service**

Create `src/gclaw/session/__init__.py`:

```python
"""Session management and compaction."""
```

Create `src/gclaw/session/service.py`:

```python
"""Session service — business logic for conversation session management."""

from __future__ import annotations

from typing import TYPE_CHECKING

from gclaw.firestore.session_repo import SessionRepo
from gclaw.models.session import (
    MessageRole,
    Session,
    SessionMessage,
    SessionStatus,
)

if TYPE_CHECKING:
    from gclaw.memory.service import MemoryService


class SessionService:
    """High-level operations on conversation sessions."""

    def __init__(
        self,
        session_repo: SessionRepo,
        memory_service: MemoryService | None = None,
        compaction_threshold: int = 50,
    ) -> None:
        self._repo = session_repo
        self._memory = memory_service
        self._compaction_threshold = compaction_threshold

    def create(
        self,
        user_id: str,
        agent_id: str | None = None,
        metadata: dict | None = None,
    ) -> Session:
        session = Session(
            user_id=user_id,
            agent_id=agent_id,
            metadata=metadata or {},
        )
        return self._repo.create(session)

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> Session:
        session = self._repo.get(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")

        msg = SessionMessage(role=MessageRole(role), content=content)
        updated = session.append_message(msg)
        return self._repo.update(updated)

    def get_history(
        self,
        session_id: str,
        limit: int | None = None,
    ) -> list[SessionMessage]:
        session = self._repo.get(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")

        if limit is not None:
            return session.get_recent_messages(limit=limit)
        return list(session.messages)

    def needs_compaction(self, session: Session) -> bool:
        """Check if a session needs mid-session compaction."""
        return session.message_count >= self._compaction_threshold

    def compact(
        self,
        session_id: str,
        summary: str,
        keep_recent: int = 10,
    ) -> Session:
        """Compact a session: store summary, keep only recent messages.

        This is mid-session compaction — the session stays active but
        older messages are replaced with a summary.
        """
        session = self._repo.get(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")

        recent = session.get_recent_messages(limit=keep_recent)
        compacted = session.model_copy(
            update={
                "messages": recent,
                "compaction_summary": summary,
            }
        )
        return self._repo.update(compacted)

    async def end_session(self, session_id: str) -> Session:
        """End a session and extract memories if memory service is available.

        This is end-of-session compaction:
        1. Send full history to Memory Bank's memories:generate
        2. Mark session as ended
        """
        session = self._repo.get(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")

        # Extract memories from conversation if memory service is available
        if self._memory is not None and session.messages:
            conversation_text = "\n".join(
                f"{m.role.value}: {m.content}" for m in session.messages
            )
            await self._memory.generate_memories(
                user_id=session.user_id,
                conversation_text=conversation_text,
            )

        ended = session.end()
        return self._repo.update(ended)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_session_service.py -v`
Expected: All 11 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/gclaw/session/ tests/test_session_service.py
git commit -m "feat: session service with create, append, history, compaction, and end-of-session memory extraction"
```

---

### Task 4: Memory Bank Client (REST API Wrapper for Vertex AI Memory Bank)

**Files:**
- Create: `src/gclaw/models/memory.py`
- Create: `src/gclaw/memory/__init__.py`
- Create: `src/gclaw/memory/client.py`
- Create: `tests/test_memory_client.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_memory_client.py`:

```python
"""Tests for Vertex AI Memory Bank REST client.

All HTTP calls are mocked — no real GCP requests.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from gclaw.models.memory import Memory, MemoryScope, MemoryTopic
from gclaw.memory.client import MemoryBankClient


@pytest.fixture
def mock_credentials():
    creds = MagicMock()
    creds.token = "test-token"
    creds.valid = True
    return creds


@pytest.fixture
def client(mock_credentials):
    return MemoryBankClient(
        project_id="test-project",
        location="us-central1",
        credentials=mock_credentials,
    )


@pytest.mark.asyncio
async def test_generate_memories(client):
    """Test memories:generate endpoint — extracts facts from conversation."""
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "generatedMemories": [
            {
                "memory": {
                    "fact": "User prefers dark mode",
                    "topic": "USER_PREFERENCES",
                    "updateTime": "2026-03-30T12:00:00Z",
                },
            },
            {
                "memory": {
                    "fact": "User's name is Sam",
                    "topic": "KEY_CONVERSATION_DETAILS",
                    "updateTime": "2026-03-30T12:00:00Z",
                },
            },
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch.object(client, "_post", new_callable=AsyncMock, return_value=mock_response):
        memories = await client.generate_memories(
            scope=MemoryScope(user_id="user_123"),
            conversation_text="User: I prefer dark mode\nAgent: Got it!",
        )

    assert len(memories) == 2
    assert memories[0].fact == "User prefers dark mode"
    assert memories[0].topic == "USER_PREFERENCES"


@pytest.mark.asyncio
async def test_retrieve_memories(client):
    """Test memories:retrieve endpoint — semantic search for relevant memories."""
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "memories": [
            {
                "fact": "User likes Italian food",
                "topic": "USER_PREFERENCES",
                "updateTime": "2026-03-30T12:00:00Z",
                "score": 0.92,
            },
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch.object(client, "_post", new_callable=AsyncMock, return_value=mock_response):
        memories = await client.retrieve_memories(
            scope=MemoryScope(user_id="user_123"),
            query="What food does the user like?",
            top_k=5,
        )

    assert len(memories) == 1
    assert memories[0].fact == "User likes Italian food"
    assert memories[0].score == 0.92


@pytest.mark.asyncio
async def test_list_memories(client):
    """Test memories:list endpoint — list all memories for a scope."""
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "memories": [
            {
                "fact": "User prefers dark mode",
                "topic": "USER_PREFERENCES",
                "updateTime": "2026-03-30T12:00:00Z",
            },
            {
                "fact": "User works at Acme Corp",
                "topic": "KEY_CONVERSATION_DETAILS",
                "updateTime": "2026-03-29T10:00:00Z",
            },
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch.object(client, "_post", new_callable=AsyncMock, return_value=mock_response):
        memories = await client.list_memories(
            scope=MemoryScope(user_id="user_123"),
        )

    assert len(memories) == 2


@pytest.mark.asyncio
async def test_retrieve_with_agent_scope(client):
    """Test retrieval with agent-specific scope."""
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"memories": []}
    mock_response.raise_for_status = MagicMock()

    with patch.object(client, "_post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
        await client.retrieve_memories(
            scope=MemoryScope(user_id="user_123", agent="workspace-mgr"),
            query="email preferences",
        )

    # Verify the scope was passed correctly
    mock_post.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_with_custom_topics(client):
    """Test generate with custom topic filtering."""
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"generatedMemories": []}
    mock_response.raise_for_status = MagicMock()

    with patch.object(client, "_post", new_callable=AsyncMock, return_value=mock_response):
        memories = await client.generate_memories(
            scope=MemoryScope(user_id="user_123"),
            conversation_text="Working on the Q2 roadmap project",
            topics=["project_context", "action_items"],
        )

    assert memories == []


def test_build_scope_dict_user_only(client):
    scope = MemoryScope(user_id="user_123")
    result = client._build_scope_dict(scope)
    assert result == {"user_id": "user_123"}


def test_build_scope_dict_with_agent(client):
    scope = MemoryScope(user_id="user_123", agent="workspace-mgr")
    result = client._build_scope_dict(scope)
    assert result == {"user_id": "user_123", "agent": "workspace-mgr"}


def test_base_url(client):
    expected = (
        "https://us-central1-aiplatform.googleapis.com/v1beta1/"
        "projects/test-project/locations/us-central1/memoryBanks/default"
    )
    assert client._base_url == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_memory_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gclaw.models.memory'`

- [ ] **Step 3: Implement memory models**

Create `src/gclaw/models/memory.py`:

```python
"""Memory models for Vertex AI Memory Bank integration."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class MemoryTopic(str, Enum):
    """Memory topics — both Google-managed and custom."""

    # Google managed
    USER_PREFERENCES = "USER_PREFERENCES"
    EXPLICIT_INSTRUCTIONS = "EXPLICIT_INSTRUCTIONS"
    KEY_CONVERSATION_DETAILS = "KEY_CONVERSATION_DETAILS"

    # Custom topics
    PROJECT_CONTEXT = "project_context"
    ACTION_ITEMS = "action_items"
    RELATIONSHIPS = "relationships"
    ROUTINES = "routines"
    DOMAIN_KNOWLEDGE = "domain_knowledge"


class MemoryScope(BaseModel):
    """Scope for memory operations.

    - user_id only: user-scoped (shared across all agents)
    - user_id + agent: agent-scoped (domain-specific per agent)
    """

    user_id: str
    agent: str | None = None


class Memory(BaseModel):
    """A single memory fact from the Memory Bank."""

    fact: str
    topic: str = ""
    update_time: str | None = None
    score: float | None = None  # relevance score from retrieve
```

- [ ] **Step 4: Implement memory bank client**

Create `src/gclaw/memory/__init__.py`:

```python
"""Vertex AI Memory Bank integration."""
```

Create `src/gclaw/memory/client.py`:

```python
"""Vertex AI Memory Bank REST API client.

Uses google.auth for credentials and httpx for async HTTP calls.
The Memory Bank API provides three key operations:
- memories:generate — extract facts from conversation text
- memories:retrieve — semantic search for relevant memories
- memories:list — list all memories for a scope

API docs: https://cloud.google.com/vertex-ai/docs/reference/rest/v1beta1/memoryBanks
"""

from __future__ import annotations

from typing import Any

import httpx
from google.auth.credentials import Credentials
from google.auth.transport.requests import Request as AuthRequest

from gclaw.models.memory import Memory, MemoryScope


class MemoryBankClient:
    """Async client for Vertex AI Memory Bank REST API."""

    def __init__(
        self,
        project_id: str,
        location: str,
        credentials: Credentials,
        memory_bank_id: str = "default",
    ) -> None:
        self._project_id = project_id
        self._location = location
        self._credentials = credentials
        self._memory_bank_id = memory_bank_id
        self._base_url = (
            f"https://{location}-aiplatform.googleapis.com/v1beta1/"
            f"projects/{project_id}/locations/{location}/"
            f"memoryBanks/{memory_bank_id}"
        )

    def _get_headers(self) -> dict[str, str]:
        """Get auth headers, refreshing credentials if needed."""
        if not self._credentials.valid:
            self._credentials.refresh(AuthRequest())
        return {
            "Authorization": f"Bearer {self._credentials.token}",
            "Content-Type": "application/json",
        }

    async def _post(self, url: str, json: dict) -> httpx.Response:
        """Make an authenticated POST request."""
        headers = self._get_headers()
        async with httpx.AsyncClient() as http:
            response = await http.post(url, json=json, headers=headers)
            response.raise_for_status()
            return response

    def _build_scope_dict(self, scope: MemoryScope) -> dict[str, str]:
        """Build the scope dict for the API request."""
        d = {"user_id": scope.user_id}
        if scope.agent is not None:
            d["agent"] = scope.agent
        return d

    async def generate_memories(
        self,
        scope: MemoryScope,
        conversation_text: str,
        topics: list[str] | None = None,
    ) -> list[Memory]:
        """Extract memories from conversation text via memories:generate.

        Args:
            scope: Memory scope (user or user+agent).
            conversation_text: The conversation to extract facts from.
            topics: Optional list of topics to focus extraction on.

        Returns:
            List of extracted Memory objects.
        """
        body: dict[str, Any] = {
            "scope": self._build_scope_dict(scope),
            "conversation": {"text": conversation_text},
        }
        if topics:
            body["topics"] = topics

        url = f"{self._base_url}/memories:generate"
        response = await self._post(url, json=body)
        data = response.json()

        memories = []
        for item in data.get("generatedMemories", []):
            mem_data = item.get("memory", {})
            memories.append(
                Memory(
                    fact=mem_data.get("fact", ""),
                    topic=mem_data.get("topic", ""),
                    update_time=mem_data.get("updateTime"),
                )
            )
        return memories

    async def retrieve_memories(
        self,
        scope: MemoryScope,
        query: str,
        top_k: int = 10,
    ) -> list[Memory]:
        """Retrieve relevant memories via semantic search.

        Args:
            scope: Memory scope (user or user+agent).
            query: Natural language query to search against.
            top_k: Maximum number of memories to return.

        Returns:
            List of Memory objects sorted by relevance.
        """
        body = {
            "scope": self._build_scope_dict(scope),
            "query": query,
            "topK": top_k,
        }

        url = f"{self._base_url}/memories:retrieve"
        response = await self._post(url, json=body)
        data = response.json()

        memories = []
        for item in data.get("memories", []):
            memories.append(
                Memory(
                    fact=item.get("fact", ""),
                    topic=item.get("topic", ""),
                    update_time=item.get("updateTime"),
                    score=item.get("score"),
                )
            )
        return memories

    async def list_memories(
        self,
        scope: MemoryScope,
    ) -> list[Memory]:
        """List all memories for a given scope.

        Args:
            scope: Memory scope (user or user+agent).

        Returns:
            List of all Memory objects in the scope.
        """
        body = {
            "scope": self._build_scope_dict(scope),
        }

        url = f"{self._base_url}/memories:list"
        response = await self._post(url, json=body)
        data = response.json()

        memories = []
        for item in data.get("memories", []):
            memories.append(
                Memory(
                    fact=item.get("fact", ""),
                    topic=item.get("topic", ""),
                    update_time=item.get("updateTime"),
                )
            )
        return memories
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_memory_client.py -v`
Expected: All 9 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/gclaw/models/memory.py src/gclaw/memory/ tests/test_memory_client.py
git commit -m "feat: Vertex AI Memory Bank REST client with generate, retrieve, and list operations"
```

---

### Task 5: Memory Service (Auto-Recall, Auto-Capture, Scoping)

**Files:**
- Create: `src/gclaw/memory/service.py`
- Create: `tests/test_memory_service.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_memory_service.py`:

```python
"""Tests for memory service — auto-recall, auto-capture, scoping."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from gclaw.models.memory import Memory, MemoryScope
from gclaw.memory.service import MemoryService


@pytest.fixture
def memory_client():
    client = MagicMock()
    client.retrieve_memories = AsyncMock(return_value=[])
    client.generate_memories = AsyncMock(return_value=[])
    client.list_memories = AsyncMock(return_value=[])
    return client


@pytest.fixture
def service(memory_client):
    return MemoryService(client=memory_client)


@pytest.mark.asyncio
async def test_recall_user_scoped(service, memory_client):
    """Auto-recall retrieves memories for user scope."""
    memory_client.retrieve_memories.return_value = [
        Memory(fact="User prefers dark mode", topic="USER_PREFERENCES", score=0.95),
        Memory(fact="User's name is Sam", topic="KEY_CONVERSATION_DETAILS", score=0.88),
    ]

    memories = await service.recall(
        user_id="user_123",
        query="What are the user's preferences?",
    )

    assert len(memories) == 2
    assert memories[0].fact == "User prefers dark mode"
    memory_client.retrieve_memories.assert_awaited_once()
    # Should use user-scoped
    call_args = memory_client.retrieve_memories.call_args
    assert call_args.kwargs["scope"].user_id == "user_123"
    assert call_args.kwargs["scope"].agent is None


@pytest.mark.asyncio
async def test_recall_agent_scoped(service, memory_client):
    """Auto-recall can include agent-specific memories."""
    memory_client.retrieve_memories.return_value = [
        Memory(fact="Email sign-off: Best regards", topic="USER_PREFERENCES", score=0.90),
    ]

    memories = await service.recall(
        user_id="user_123",
        query="email style",
        agent_id="workspace-mgr",
    )

    assert len(memories) == 1
    call_args = memory_client.retrieve_memories.call_args
    assert call_args.kwargs["scope"].agent == "workspace-mgr"


@pytest.mark.asyncio
async def test_recall_merged_scopes(service, memory_client):
    """When agent_id is set, recall merges both user-scoped and agent-scoped."""
    user_memories = [
        Memory(fact="User prefers dark mode", topic="USER_PREFERENCES", score=0.95),
    ]
    agent_memories = [
        Memory(fact="Email sign-off: Best", topic="USER_PREFERENCES", score=0.90),
    ]
    # First call = agent-scoped, second call = user-scoped
    memory_client.retrieve_memories.side_effect = [agent_memories, user_memories]

    memories = await service.recall(
        user_id="user_123",
        query="preferences",
        agent_id="workspace-mgr",
        merge_user_scope=True,
    )

    # Should have merged both scopes
    assert len(memories) == 2
    assert memory_client.retrieve_memories.await_count == 2


@pytest.mark.asyncio
async def test_capture_fires_generate(service, memory_client):
    """Auto-capture sends conversation to memories:generate."""
    memory_client.generate_memories.return_value = [
        Memory(fact="User likes coffee", topic="USER_PREFERENCES"),
    ]

    result = await service.capture(
        user_id="user_123",
        conversation_text="User: I really like coffee\nAgent: Noted!",
    )

    assert len(result) == 1
    memory_client.generate_memories.assert_awaited_once()


@pytest.mark.asyncio
async def test_capture_with_agent_scope(service, memory_client):
    """Auto-capture can target agent-specific scope."""
    memory_client.generate_memories.return_value = []

    await service.capture(
        user_id="user_123",
        conversation_text="Some conversation",
        agent_id="dev-mgr",
    )

    call_args = memory_client.generate_memories.call_args
    assert call_args.kwargs["scope"].agent == "dev-mgr"


@pytest.mark.asyncio
async def test_capture_with_topics(service, memory_client):
    """Auto-capture can specify topics to focus on."""
    memory_client.generate_memories.return_value = []

    await service.capture(
        user_id="user_123",
        conversation_text="Working on Q2 roadmap",
        topics=["project_context", "action_items"],
    )

    call_args = memory_client.generate_memories.call_args
    assert call_args.kwargs["topics"] == ["project_context", "action_items"]


@pytest.mark.asyncio
async def test_generate_memories_delegates(service, memory_client):
    """generate_memories is the end-of-session extraction call."""
    memory_client.generate_memories.return_value = [
        Memory(fact="Important fact", topic="KEY_CONVERSATION_DETAILS"),
    ]

    result = await service.generate_memories(
        user_id="user_123",
        conversation_text="Full session text here",
    )

    assert len(result) == 1
    memory_client.generate_memories.assert_awaited_once()


@pytest.mark.asyncio
async def test_capture_error_is_suppressed(service, memory_client):
    """Auto-capture errors should not propagate (fire-and-forget)."""
    memory_client.generate_memories.side_effect = Exception("API error")

    # Should not raise
    result = await service.capture(
        user_id="user_123",
        conversation_text="Some text",
    )

    assert result == []


@pytest.mark.asyncio
async def test_format_memories_for_prompt(service):
    """Format memories into injectable prompt text."""
    memories = [
        Memory(fact="User prefers dark mode", topic="USER_PREFERENCES"),
        Memory(fact="User works at Acme", topic="KEY_CONVERSATION_DETAILS"),
    ]

    formatted = service.format_for_prompt(memories)

    assert "User prefers dark mode" in formatted
    assert "User works at Acme" in formatted
    assert "USER_PREFERENCES" in formatted
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_memory_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gclaw.memory.service'`

- [ ] **Step 3: Implement memory service**

Create `src/gclaw/memory/service.py`:

```python
"""Memory service — auto-recall, auto-capture, and scoping logic.

This service wraps the MemoryBankClient and provides higher-level
operations used by the AgentRunner and HeartbeatContextGatherer:

- recall: retrieve relevant memories before an agent turn
- capture: extract facts from conversation after a turn (fire-and-forget)
- generate_memories: full extraction at end of session
- format_for_prompt: format memories for injection into system prompts
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from gclaw.models.memory import Memory, MemoryScope

if TYPE_CHECKING:
    from gclaw.memory.client import MemoryBankClient

logger = logging.getLogger(__name__)


class MemoryService:
    """High-level memory operations with scoping and error handling."""

    def __init__(self, client: MemoryBankClient) -> None:
        self._client = client

    async def recall(
        self,
        user_id: str,
        query: str,
        agent_id: str | None = None,
        top_k: int = 10,
        merge_user_scope: bool = False,
    ) -> list[Memory]:
        """Auto-recall: retrieve relevant memories before an agent turn.

        Args:
            user_id: The user to retrieve memories for.
            query: Natural language query (typically the user's message).
            agent_id: If set, retrieve from agent-scoped memories.
            top_k: Max memories to return per scope.
            merge_user_scope: If True and agent_id is set, also retrieve
                user-scoped memories and merge the results.

        Returns:
            List of relevant Memory objects sorted by score.
        """
        if agent_id and merge_user_scope:
            # Retrieve from both agent scope and user scope
            agent_scope = MemoryScope(user_id=user_id, agent=agent_id)
            user_scope = MemoryScope(user_id=user_id)

            agent_memories = await self._client.retrieve_memories(
                scope=agent_scope, query=query, top_k=top_k,
            )
            user_memories = await self._client.retrieve_memories(
                scope=user_scope, query=query, top_k=top_k,
            )

            # Merge and deduplicate by fact text
            seen = set()
            merged = []
            for m in agent_memories + user_memories:
                if m.fact not in seen:
                    seen.add(m.fact)
                    merged.append(m)
            return merged

        scope = MemoryScope(user_id=user_id, agent=agent_id)
        return await self._client.retrieve_memories(
            scope=scope, query=query, top_k=top_k,
        )

    async def capture(
        self,
        user_id: str,
        conversation_text: str,
        agent_id: str | None = None,
        topics: list[str] | None = None,
    ) -> list[Memory]:
        """Auto-capture: fire-and-forget extraction after each turn.

        Errors are logged and suppressed — capture should never break
        the main conversation flow.

        Args:
            user_id: The user to store memories for.
            conversation_text: Text of the recent exchange.
            agent_id: If set, store in agent-scoped memories.
            topics: Optional topics to focus extraction on.

        Returns:
            List of extracted memories (empty on error).
        """
        try:
            scope = MemoryScope(user_id=user_id, agent=agent_id)
            return await self._client.generate_memories(
                scope=scope,
                conversation_text=conversation_text,
                topics=topics,
            )
        except Exception:
            logger.warning(
                "Memory capture failed for user %s (agent=%s)",
                user_id,
                agent_id,
                exc_info=True,
            )
            return []

    async def generate_memories(
        self,
        user_id: str,
        conversation_text: str,
        agent_id: str | None = None,
    ) -> list[Memory]:
        """End-of-session memory extraction.

        Unlike capture(), this raises on error — callers should handle it.

        Args:
            user_id: The user to store memories for.
            conversation_text: Full session conversation text.
            agent_id: If set, store in agent-scoped memories.

        Returns:
            List of extracted memories.
        """
        scope = MemoryScope(user_id=user_id, agent=agent_id)
        return await self._client.generate_memories(
            scope=scope,
            conversation_text=conversation_text,
        )

    def format_for_prompt(self, memories: list[Memory]) -> str:
        """Format memories into text suitable for system prompt injection.

        Groups memories by topic for readability.
        """
        if not memories:
            return ""

        # Group by topic
        by_topic: dict[str, list[str]] = {}
        for m in memories:
            topic = m.topic or "general"
            if topic not in by_topic:
                by_topic[topic] = []
            by_topic[topic].append(m.fact)

        lines = []
        for topic, facts in by_topic.items():
            lines.append(f"**{topic}:**")
            for fact in facts:
                lines.append(f"- {fact}")
            lines.append("")

        return "\n".join(lines).strip()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_memory_service.py -v`
Expected: All 10 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/gclaw/memory/service.py tests/test_memory_service.py
git commit -m "feat: memory service with auto-recall, auto-capture, scoping, and prompt formatting"
```

---

### Task 6: Skill Model + Registry

**Files:**
- Create: `src/gclaw/models/skill.py`
- Create: `src/gclaw/firestore/skill_repo.py`
- Create: `src/gclaw/skill/__init__.py`
- Create: `src/gclaw/skill/registry.py`
- Create: `tests/test_skill_model.py`
- Create: `tests/test_skill_registry.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_skill_model.py`:

```python
"""Tests for skill model."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from gclaw.models.skill import (
    Skill,
    SkillTrigger,
    TriggerMode,
    SkillSource,
)


def test_create_minimal_skill():
    skill = Skill(
        name="email-drafter",
        description="Draft professional emails matching user's tone",
    )
    assert skill.name == "email-drafter"
    assert skill.description == "Draft professional emails matching user's tone"
    assert skill.source == SkillSource.BUILTIN
    assert skill.tools_required == []
    assert skill.agents_granted == []


def test_create_full_skill():
    skill = Skill(
        name="email-drafter",
        description="Draft professional emails",
        version="1.2.0",
        trigger=SkillTrigger(
            mode=TriggerMode.BOTH,
            contexts=["composing email", "replying to thread"],
            command="/draft-email",
        ),
        config={"formality": "professional", "max_length": 500},
        tools_required=["gmail", "contacts"],
        agents_granted=["workspace-mgr", "comms-mgr"],
        source=SkillSource.BUILTIN,
        instructions_path="skills/email-drafter/instructions.md",
        examples_path="skills/email-drafter/examples.md",
    )
    assert skill.trigger.mode == TriggerMode.BOTH
    assert len(skill.trigger.contexts) == 2
    assert skill.trigger.command == "/draft-email"
    assert skill.config["formality"] == "professional"
    assert "gmail" in skill.tools_required
    assert "workspace-mgr" in skill.agents_granted


def test_skill_trigger_auto_mode():
    trigger = SkillTrigger(
        mode=TriggerMode.AUTO,
        contexts=["scheduling meeting"],
    )
    assert trigger.mode == TriggerMode.AUTO
    assert trigger.command is None


def test_skill_to_firestore_dict():
    skill = Skill(
        name="test-skill",
        description="A test skill",
        tools_required=["gmail"],
    )
    d = skill.to_firestore_dict()
    assert d["name"] == "test-skill"
    assert d["tools_required"] == ["gmail"]


def test_skill_from_firestore_dict():
    d = {
        "name": "email-drafter",
        "description": "Draft emails",
        "version": "1.0.0",
        "trigger": {
            "mode": "auto",
            "contexts": ["composing email"],
            "command": None,
        },
        "config": {},
        "tools_required": ["gmail"],
        "agents_granted": ["workspace-mgr"],
        "source": "builtin",
        "instructions_path": None,
        "examples_path": None,
    }
    skill = Skill.from_firestore_dict(d)
    assert skill.name == "email-drafter"
    assert skill.trigger.mode == TriggerMode.AUTO
    assert skill.source == SkillSource.BUILTIN


def test_skill_is_granted_to():
    skill = Skill(
        name="test",
        description="Test",
        agents_granted=["workspace-mgr", "comms-mgr"],
    )
    assert skill.is_granted_to("workspace-mgr") is True
    assert skill.is_granted_to("dev-mgr") is False


def test_skill_matches_context():
    skill = Skill(
        name="test",
        description="Test",
        trigger=SkillTrigger(
            mode=TriggerMode.AUTO,
            contexts=["composing email", "replying to thread"],
        ),
    )
    assert skill.matches_context("composing email") is True
    assert skill.matches_context("scheduling meeting") is False
    # Partial match
    assert skill.matches_context("composing") is True
```

Create `tests/test_skill_registry.py`:

```python
"""Tests for skill registry."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from gclaw.models.skill import Skill, SkillSource, SkillTrigger, TriggerMode
from gclaw.skill.registry import SkillRegistry


@pytest.fixture
def skill_repo():
    return MagicMock()


@pytest.fixture
def registry(skill_repo):
    return SkillRegistry(skill_repo=skill_repo)


def test_register_skill(registry, skill_repo):
    skill = Skill(
        name="email-drafter",
        description="Draft emails",
        agents_granted=["workspace-mgr"],
    )
    skill_repo.save.side_effect = lambda s: s

    result = registry.register(skill)

    assert result.name == "email-drafter"
    skill_repo.save.assert_called_once()


def test_get_skill(registry, skill_repo):
    skill_repo.get.return_value = Skill(
        name="email-drafter",
        description="Draft emails",
    )

    result = registry.get("email-drafter")

    assert result is not None
    assert result.name == "email-drafter"


def test_get_nonexistent_skill(registry, skill_repo):
    skill_repo.get.return_value = None

    result = registry.get("nonexistent")

    assert result is None


def test_list_all(registry, skill_repo):
    skill_repo.list_all.return_value = [
        Skill(name="skill-1", description="First"),
        Skill(name="skill-2", description="Second"),
    ]

    skills = registry.list_all()

    assert len(skills) == 2


def test_list_for_agent(registry, skill_repo):
    skill_repo.list_all.return_value = [
        Skill(name="email-drafter", description="Draft emails",
              agents_granted=["workspace-mgr"]),
        Skill(name="code-review", description="Review code",
              agents_granted=["dev-mgr"]),
        Skill(name="research", description="Web research",
              agents_granted=["workspace-mgr", "research-mgr"]),
    ]

    skills = registry.list_for_agent("workspace-mgr")

    assert len(skills) == 2
    names = [s.name for s in skills]
    assert "email-drafter" in names
    assert "research" in names
    assert "code-review" not in names


def test_unregister_skill(registry, skill_repo):
    registry.unregister("email-drafter")
    skill_repo.delete.assert_called_once_with("email-drafter")


def test_load_builtins(registry, skill_repo, tmp_path):
    """Test loading built-in skills from a directory."""
    # Create a skill directory
    skill_dir = tmp_path / "skills" / "test-skill"
    skill_dir.mkdir(parents=True)
    skill_json = skill_dir / "skill.json"
    skill_json.write_text(
        '{"name": "test-skill", "description": "A test skill", '
        '"version": "1.0.0", "trigger": {"mode": "manual", "contexts": [], "command": "/test"}, '
        '"config": {}, "tools_required": [], "agents_granted": ["workspace-mgr"], '
        '"source": "builtin"}'
    )

    skill_repo.save.side_effect = lambda s: s
    skill_repo.get.return_value = None

    loaded = registry.load_builtins(str(tmp_path / "skills"))

    assert len(loaded) == 1
    assert loaded[0].name == "test-skill"
    skill_repo.save.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_skill_model.py tests/test_skill_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gclaw.models.skill'`

- [ ] **Step 3: Implement skill model**

Create `src/gclaw/models/skill.py`:

```python
"""Skill model for the capability layer."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field
from typing_extensions import Self


class TriggerMode(str, Enum):
    AUTO = "auto"
    MANUAL = "manual"
    BOTH = "both"


class SkillSource(str, Enum):
    BUILTIN = "builtin"
    IMPORTED = "imported"
    CUSTOM = "custom"


class SkillTrigger(BaseModel):
    """How and when a skill is invoked."""

    mode: TriggerMode = TriggerMode.MANUAL
    contexts: list[str] = Field(default_factory=list)
    command: str | None = None


class Skill(BaseModel):
    """A skill definition — a modular, composable capability.

    Skills are compound workflows with judgment, not just atomic API calls.
    They include instructions, examples, config, and tool orchestration.
    """

    name: str
    description: str
    version: str = "1.0.0"
    trigger: SkillTrigger = Field(default_factory=SkillTrigger)
    config: dict = Field(default_factory=dict)
    tools_required: list[str] = Field(default_factory=list)
    agents_granted: list[str] = Field(default_factory=list)
    source: SkillSource = SkillSource.BUILTIN
    instructions_path: str | None = None
    examples_path: str | None = None

    def is_granted_to(self, agent_name: str) -> bool:
        """Check if this skill is granted to the given agent."""
        return agent_name in self.agents_granted

    def matches_context(self, context: str) -> bool:
        """Check if the given context matches any of this skill's trigger contexts."""
        context_lower = context.lower()
        for trigger_ctx in self.trigger.contexts:
            if context_lower in trigger_ctx.lower() or trigger_ctx.lower() in context_lower:
                return True
        return False

    def to_firestore_dict(self) -> dict:
        return self.model_dump(mode="json")

    @classmethod
    def from_firestore_dict(cls, data: dict) -> Self:
        return cls(**data)
```

- [ ] **Step 4: Implement skill Firestore repository**

Create `src/gclaw/firestore/skill_repo.py`:

```python
"""Skill registry CRUD operations on Firestore.

Collection path: users/{userId}/skills/{skillName}
"""

from __future__ import annotations

from google.cloud.firestore import Client as FirestoreClient

from gclaw.models.skill import Skill


class SkillRepo:
    """Synchronous Firestore repository for skill definitions."""

    def __init__(self, db: FirestoreClient, user_id: str) -> None:
        self._db = db
        self._user_id = user_id

    def _collection_ref(self):
        return (
            self._db.collection("users")
            .document(self._user_id)
            .collection("skills")
        )

    def save(self, skill: Skill) -> Skill:
        """Save or overwrite a skill definition."""
        doc_ref = self._collection_ref().document(skill.name)
        doc_ref.set(skill.to_firestore_dict())
        return skill

    def get(self, skill_name: str) -> Skill | None:
        doc = self._collection_ref().document(skill_name).get()
        if not doc.exists:
            return None
        return Skill.from_firestore_dict(doc.to_dict())

    def delete(self, skill_name: str) -> None:
        self._collection_ref().document(skill_name).delete()

    def list_all(self) -> list[Skill]:
        docs = self._collection_ref().stream()
        return [Skill.from_firestore_dict(doc.to_dict()) for doc in docs]
```

- [ ] **Step 5: Implement skill registry**

Create `src/gclaw/skill/__init__.py`:

```python
"""Skill system — modular capabilities for agents."""
```

Create `src/gclaw/skill/registry.py`:

```python
"""Skill registry — manages skill definitions from files and Firestore."""

from __future__ import annotations

import json
import logging
import os

from gclaw.firestore.skill_repo import SkillRepo
from gclaw.models.skill import Skill

logger = logging.getLogger(__name__)


class SkillRegistry:
    """Central registry for skill discovery and management."""

    def __init__(self, skill_repo: SkillRepo) -> None:
        self._repo = skill_repo

    def register(self, skill: Skill) -> Skill:
        """Register a skill in the Firestore registry."""
        return self._repo.save(skill)

    def get(self, skill_name: str) -> Skill | None:
        """Get a skill by name."""
        return self._repo.get(skill_name)

    def list_all(self) -> list[Skill]:
        """List all registered skills."""
        return self._repo.list_all()

    def list_for_agent(self, agent_name: str) -> list[Skill]:
        """List skills granted to a specific agent."""
        all_skills = self._repo.list_all()
        return [s for s in all_skills if s.is_granted_to(agent_name)]

    def unregister(self, skill_name: str) -> None:
        """Remove a skill from the registry."""
        self._repo.delete(skill_name)

    def load_builtins(self, skills_dir: str) -> list[Skill]:
        """Load built-in skills from the skills/ directory.

        Each skill subdirectory should contain a skill.json file.
        Skills are registered in Firestore if not already present.

        Args:
            skills_dir: Path to the skills/ directory.

        Returns:
            List of loaded Skill objects.
        """
        loaded = []
        if not os.path.isdir(skills_dir):
            logger.warning("Skills directory not found: %s", skills_dir)
            return loaded

        for entry in os.listdir(skills_dir):
            skill_path = os.path.join(skills_dir, entry)
            if not os.path.isdir(skill_path):
                continue

            manifest_path = os.path.join(skill_path, "skill.json")
            if not os.path.isfile(manifest_path):
                logger.debug("No skill.json in %s, skipping", skill_path)
                continue

            try:
                with open(manifest_path) as f:
                    data = json.load(f)
                skill = Skill.from_firestore_dict(data)
                # Set paths relative to the skill directory
                if skill.instructions_path is None:
                    instructions = os.path.join(skill_path, "instructions.md")
                    if os.path.isfile(instructions):
                        skill = skill.model_copy(
                            update={"instructions_path": instructions}
                        )
                if skill.examples_path is None:
                    examples = os.path.join(skill_path, "examples.md")
                    if os.path.isfile(examples):
                        skill = skill.model_copy(
                            update={"examples_path": examples}
                        )

                self._repo.save(skill)
                loaded.append(skill)
                logger.info("Loaded built-in skill: %s", skill.name)
            except Exception:
                logger.warning(
                    "Failed to load skill from %s",
                    manifest_path,
                    exc_info=True,
                )

        return loaded
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_skill_model.py tests/test_skill_registry.py -v`
Expected: All 15 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/gclaw/models/skill.py src/gclaw/firestore/skill_repo.py src/gclaw/skill/ tests/test_skill_model.py tests/test_skill_registry.py
git commit -m "feat: skill model, Firestore repository, and registry with built-in loading"
```

---

### Task 7: Skill Loader + Discovery

**Files:**
- Create: `src/gclaw/skill/loader.py`
- Create: `src/gclaw/skill/discovery.py`
- Create: `tests/test_skill_loader.py`
- Create: `tests/test_skill_discovery.py`
- Create: `skills/email-drafter/skill.json`
- Create: `skills/email-drafter/instructions.md`
- Create: `skills/email-drafter/examples.md`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_skill_loader.py`:

```python
"""Tests for skill loader — reads skill files and builds prompt sections."""

from __future__ import annotations

import pytest

from gclaw.models.skill import Skill, SkillTrigger, TriggerMode
from gclaw.skill.loader import SkillLoader


@pytest.fixture
def skill_dir(tmp_path):
    """Create a skill directory with instructions and examples."""
    skill_path = tmp_path / "skills" / "email-drafter"
    skill_path.mkdir(parents=True)

    (skill_path / "instructions.md").write_text(
        "# Email Drafter\n\n"
        "When drafting an email:\n"
        "1. Match the user's tone and formality level\n"
        "2. Keep it concise\n"
        "3. Always include a greeting and sign-off\n"
    )
    (skill_path / "examples.md").write_text(
        "# Examples\n\n"
        "## Professional email\n"
        "Subject: Q2 Roadmap Update\n"
        "Hi Sarah, ...\n"
    )
    return tmp_path


@pytest.fixture
def loader():
    return SkillLoader()


def test_load_instructions(loader, skill_dir):
    skill = Skill(
        name="email-drafter",
        description="Draft emails",
        instructions_path=str(skill_dir / "skills" / "email-drafter" / "instructions.md"),
    )

    instructions = loader.load_instructions(skill)

    assert "Email Drafter" in instructions
    assert "Match the user's tone" in instructions


def test_load_examples(loader, skill_dir):
    skill = Skill(
        name="email-drafter",
        description="Draft emails",
        examples_path=str(skill_dir / "skills" / "email-drafter" / "examples.md"),
    )

    examples = loader.load_examples(skill)

    assert "Professional email" in examples
    assert "Q2 Roadmap Update" in examples


def test_load_missing_instructions(loader):
    skill = Skill(
        name="email-drafter",
        description="Draft emails",
        instructions_path="/nonexistent/path/instructions.md",
    )

    instructions = loader.load_instructions(skill)

    assert instructions == ""


def test_load_no_path(loader):
    skill = Skill(
        name="email-drafter",
        description="Draft emails",
    )

    assert loader.load_instructions(skill) == ""
    assert loader.load_examples(skill) == ""


def test_build_skill_prompt_section(loader, skill_dir):
    skill = Skill(
        name="email-drafter",
        description="Draft professional emails matching user's tone",
        config={"formality": "professional"},
        instructions_path=str(skill_dir / "skills" / "email-drafter" / "instructions.md"),
        examples_path=str(skill_dir / "skills" / "email-drafter" / "examples.md"),
    )

    section = loader.build_prompt_section(skill)

    assert "## Skill: email-drafter" in section
    assert "Draft professional emails" in section
    assert "Email Drafter" in section
    assert "Professional email" in section
    assert "formality" in section


def test_build_prompt_section_minimal(loader):
    skill = Skill(
        name="test-skill",
        description="A minimal skill",
    )

    section = loader.build_prompt_section(skill)

    assert "## Skill: test-skill" in section
    assert "A minimal skill" in section


def test_build_multi_skill_prompt(loader, skill_dir):
    skills = [
        Skill(
            name="email-drafter",
            description="Draft emails",
            instructions_path=str(skill_dir / "skills" / "email-drafter" / "instructions.md"),
        ),
        Skill(
            name="research",
            description="Web research",
        ),
    ]

    prompt = loader.build_skills_prompt(skills)

    assert "# Available Skills" in prompt
    assert "email-drafter" in prompt
    assert "research" in prompt
```

Create `tests/test_skill_discovery.py`:

```python
"""Tests for skill discovery — find skills by context."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from gclaw.models.skill import Skill, SkillTrigger, TriggerMode
from gclaw.skill.discovery import SkillDiscovery


@pytest.fixture
def skill_registry():
    return MagicMock()


@pytest.fixture
def discovery(skill_registry):
    return SkillDiscovery(registry=skill_registry)


def test_discover_by_context(discovery, skill_registry):
    skill_registry.list_for_agent.return_value = [
        Skill(
            name="email-drafter",
            description="Draft professional emails",
            trigger=SkillTrigger(
                mode=TriggerMode.AUTO,
                contexts=["composing email", "replying to thread"],
            ),
            agents_granted=["workspace-mgr"],
        ),
        Skill(
            name="meeting-scheduler",
            description="Schedule meetings",
            trigger=SkillTrigger(
                mode=TriggerMode.AUTO,
                contexts=["scheduling meeting", "calendar management"],
            ),
            agents_granted=["workspace-mgr"],
        ),
    ]

    matches = discovery.discover(
        agent_name="workspace-mgr",
        context="composing email to client",
    )

    assert len(matches) == 1
    assert matches[0].name == "email-drafter"


def test_discover_no_matches(discovery, skill_registry):
    skill_registry.list_for_agent.return_value = [
        Skill(
            name="email-drafter",
            description="Draft emails",
            trigger=SkillTrigger(
                mode=TriggerMode.AUTO,
                contexts=["composing email"],
            ),
            agents_granted=["workspace-mgr"],
        ),
    ]

    matches = discovery.discover(
        agent_name="workspace-mgr",
        context="writing code",
    )

    assert len(matches) == 0


def test_discover_by_description(discovery, skill_registry):
    """Fall back to description-based matching if no context match."""
    skill_registry.list_for_agent.return_value = [
        Skill(
            name="research-summarizer",
            description="Summarize research findings into concise reports",
            trigger=SkillTrigger(mode=TriggerMode.AUTO, contexts=[]),
            agents_granted=["research-mgr"],
        ),
    ]

    matches = discovery.discover(
        agent_name="research-mgr",
        context="summarize research",
    )

    assert len(matches) == 1
    assert matches[0].name == "research-summarizer"


def test_discover_manual_only_excluded(discovery, skill_registry):
    """Manual-only skills should not be auto-discovered."""
    skill_registry.list_for_agent.return_value = [
        Skill(
            name="custom-tool",
            description="A manual tool",
            trigger=SkillTrigger(
                mode=TriggerMode.MANUAL,
                contexts=["any context"],
                command="/custom",
            ),
            agents_granted=["workspace-mgr"],
        ),
    ]

    matches = discovery.discover(
        agent_name="workspace-mgr",
        context="any context here",
    )

    assert len(matches) == 0


def test_discover_by_command(discovery, skill_registry):
    """Direct command invocation lookup."""
    skill_registry.list_for_agent.return_value = [
        Skill(
            name="email-drafter",
            description="Draft emails",
            trigger=SkillTrigger(
                mode=TriggerMode.BOTH,
                contexts=["composing email"],
                command="/draft-email",
            ),
            agents_granted=["workspace-mgr"],
        ),
        Skill(
            name="other-skill",
            description="Other",
            trigger=SkillTrigger(
                mode=TriggerMode.MANUAL,
                command="/other",
            ),
            agents_granted=["workspace-mgr"],
        ),
    ]

    match = discovery.find_by_command(
        agent_name="workspace-mgr",
        command="/draft-email",
    )

    assert match is not None
    assert match.name == "email-drafter"


def test_find_by_command_not_found(discovery, skill_registry):
    skill_registry.list_for_agent.return_value = []

    match = discovery.find_by_command(
        agent_name="workspace-mgr",
        command="/nonexistent",
    )

    assert match is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_skill_loader.py tests/test_skill_discovery.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gclaw.skill.loader'`

- [ ] **Step 3: Implement skill loader**

Create `src/gclaw/skill/loader.py`:

```python
"""Skill loader — reads skill files and builds prompt sections.

Each skill has:
- skill.json — manifest with name, description, trigger, config, grants
- instructions.md — detailed instructions for how to perform the skill
- examples.md — few-shot examples
"""

from __future__ import annotations

import json
import logging
import os

from gclaw.models.skill import Skill

logger = logging.getLogger(__name__)


class SkillLoader:
    """Loads skill files and builds prompt-injectable sections."""

    def load_instructions(self, skill: Skill) -> str:
        """Load the instructions.md file for a skill."""
        if skill.instructions_path is None:
            return ""
        return self._read_file(skill.instructions_path)

    def load_examples(self, skill: Skill) -> str:
        """Load the examples.md file for a skill."""
        if skill.examples_path is None:
            return ""
        return self._read_file(skill.examples_path)

    def build_prompt_section(self, skill: Skill) -> str:
        """Build a prompt section for a single skill.

        Format:
            ## Skill: <name>
            <description>

            ### Configuration
            <config as key-value pairs>

            ### Instructions
            <instructions.md content>

            ### Examples
            <examples.md content>
        """
        parts = [
            f"## Skill: {skill.name}",
            skill.description,
        ]

        if skill.config:
            parts.append("")
            parts.append("### Configuration")
            for key, value in skill.config.items():
                parts.append(f"- {key}: {value}")

        instructions = self.load_instructions(skill)
        if instructions:
            parts.append("")
            parts.append("### Instructions")
            parts.append(instructions)

        examples = self.load_examples(skill)
        if examples:
            parts.append("")
            parts.append("### Examples")
            parts.append(examples)

        return "\n".join(parts)

    def build_skills_prompt(self, skills: list[Skill]) -> str:
        """Build a combined prompt section for multiple skills.

        Args:
            skills: List of skills to include in the prompt.

        Returns:
            Formatted skills section for injection into system prompt.
        """
        if not skills:
            return ""

        sections = ["# Available Skills", ""]
        for skill in skills:
            sections.append(self.build_prompt_section(skill))
            sections.append("")

        return "\n".join(sections).strip()

    def _read_file(self, path: str) -> str:
        """Read a file, returning empty string if not found."""
        if not os.path.isfile(path):
            logger.debug("Skill file not found: %s", path)
            return ""
        with open(path) as f:
            return f.read()
```

- [ ] **Step 4: Implement skill discovery**

Create `src/gclaw/skill/discovery.py`:

```python
"""Skill discovery — find skills by context for dynamic invocation.

Skills can be discovered by:
1. Context matching — user's current context matches skill trigger contexts
2. Description matching — fallback keyword matching against skill descriptions
3. Command matching — direct /command invocation
"""

from __future__ import annotations

import logging

from gclaw.models.skill import Skill, TriggerMode
from gclaw.skill.registry import SkillRegistry

logger = logging.getLogger(__name__)


class SkillDiscovery:
    """Discovers relevant skills based on context."""

    def __init__(self, registry: SkillRegistry) -> None:
        self._registry = registry

    def discover(
        self,
        agent_name: str,
        context: str,
    ) -> list[Skill]:
        """Find skills matching the current context.

        Only auto or both trigger modes are considered — manual-only
        skills must be invoked via command.

        Args:
            agent_name: The agent looking for skills.
            context: Description of what the agent is currently doing.

        Returns:
            List of matching skills, ordered by relevance.
        """
        available = self._registry.list_for_agent(agent_name)
        matches = []

        for skill in available:
            # Skip manual-only skills
            if skill.trigger.mode == TriggerMode.MANUAL:
                continue

            # Try context match first
            if skill.matches_context(context):
                matches.append(skill)
                continue

            # Fall back to description keyword matching
            if self._description_matches(skill.description, context):
                matches.append(skill)

        return matches

    def find_by_command(
        self,
        agent_name: str,
        command: str,
    ) -> Skill | None:
        """Find a skill by its slash command.

        Args:
            agent_name: The agent invoking the command.
            command: The slash command (e.g., "/draft-email").

        Returns:
            The matching Skill, or None.
        """
        available = self._registry.list_for_agent(agent_name)
        for skill in available:
            if skill.trigger.command == command:
                return skill
        return None

    def _description_matches(self, description: str, context: str) -> bool:
        """Simple keyword matching between description and context."""
        desc_words = set(description.lower().split())
        context_words = set(context.lower().split())
        # Match if at least 2 significant words overlap
        overlap = desc_words & context_words
        # Filter out common stop words
        stop_words = {"a", "an", "the", "is", "are", "to", "for", "and", "or", "of", "in", "on", "with"}
        significant = overlap - stop_words
        return len(significant) >= 2
```

- [ ] **Step 5: Create example built-in skill**

Create `skills/email-drafter/skill.json`:

```json
{
    "name": "email-drafter",
    "description": "Draft professional emails matching the user's tone and style",
    "version": "1.0.0",
    "trigger": {
        "mode": "both",
        "contexts": ["composing email", "replying to thread", "drafting message"],
        "command": "/draft-email"
    },
    "config": {
        "formality": "professional",
        "max_length": 500
    },
    "tools_required": ["gmail", "contacts"],
    "agents_granted": ["workspace-mgr", "comms-mgr"],
    "source": "builtin"
}
```

Create `skills/email-drafter/instructions.md`:

```markdown
# Email Drafter Skill

When drafting an email for the user:

1. **Match their tone** — check soul preferences for formality, greeting style, and sign-off
2. **Be concise** — respect the configured max_length
3. **Structure well** — clear subject line, greeting, body paragraphs, sign-off
4. **Context-aware** — reference previous conversations or attached context when relevant
5. **Ask if unsure** — if the intent is ambiguous, ask for clarification before drafting

## Formality Levels

- **casual**: Hey/Hi, first names, relaxed grammar, emoji ok
- **professional**: Hi/Hello, respectful tone, proper grammar
- **formal**: Dear, full names/titles, structured paragraphs
```

Create `skills/email-drafter/examples.md`:

```markdown
# Email Drafter Examples

## Professional reply to a meeting request

**Context:** Sarah asked to meet about Q2 roadmap

**Draft:**
Subject: Re: Q2 Roadmap Discussion

Hi Sarah,

Thanks for reaching out. I'd be happy to discuss the Q2 roadmap.

How about Tuesday at 2pm? I'll prepare a summary of our current progress and key decision points.

Best regards,
[User]

## Casual follow-up

**Context:** Following up with a teammate about a code review

**Draft:**
Subject: Re: PR #142 Review

Hey Alex,

Just checking in on the PR review — any blockers I can help with? Happy to jump on a quick call if that's easier.

Thanks!
[User]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_skill_loader.py tests/test_skill_discovery.py -v`
Expected: All 13 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/gclaw/skill/loader.py src/gclaw/skill/discovery.py skills/ tests/test_skill_loader.py tests/test_skill_discovery.py
git commit -m "feat: skill loader with prompt building and skill discovery with context matching"
```

---

### Task 8: Integration — Update AgentRunner with Memory Hooks

**Files:**
- Modify: `src/gclaw/dispatch/runner.py`
- Create: `tests/test_runner_memory.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_runner_memory.py`:

```python
"""Tests for AgentRunner memory integration.

Tests that the runner performs auto-recall before a turn and
auto-capture after a turn when a MemoryService is provided.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

from gclaw.models.memory import Memory
from gclaw.dispatch.runner import AgentRunner, AgentResponse


@pytest.fixture
def mock_agent():
    return MagicMock()


@pytest.fixture
def mock_session_service():
    return MagicMock()


@pytest.fixture
def memory_service():
    svc = MagicMock()
    svc.recall = AsyncMock(return_value=[
        Memory(fact="User prefers concise answers", topic="USER_PREFERENCES"),
    ])
    svc.capture = AsyncMock(return_value=[])
    svc.format_for_prompt = MagicMock(return_value="- User prefers concise answers")
    return svc


@pytest.fixture
def runner_with_memory(mock_agent, mock_session_service, memory_service):
    runner = AgentRunner(
        agent=mock_agent,
        app_name="gclaw",
        session_service=mock_session_service,
        memory_service=memory_service,
    )
    return runner


@pytest.fixture
def runner_without_memory(mock_agent, mock_session_service):
    runner = AgentRunner(
        agent=mock_agent,
        app_name="gclaw",
        session_service=mock_session_service,
    )
    return runner


@pytest.mark.asyncio
async def test_run_with_memory_recall(runner_with_memory, memory_service):
    """Memory recall is called before the agent turn."""
    # Mock the internal runner to return a simple response
    mock_event = MagicMock()
    mock_event.content = MagicMock()
    mock_event.content.parts = [MagicMock(text="Hello!", function_call=None)]
    mock_event.is_final_response.return_value = True

    async def mock_run_async(**kwargs):
        yield mock_event

    runner_with_memory._runner = MagicMock()
    runner_with_memory._runner.run_async = mock_run_async

    response = await runner_with_memory.run(
        user_id="user_123",
        session_id="sess_1",
        message="What are my preferences?",
    )

    memory_service.recall.assert_awaited_once_with(
        user_id="user_123",
        query="What are my preferences?",
    )


@pytest.mark.asyncio
async def test_run_with_memory_capture(runner_with_memory, memory_service):
    """Memory capture is called after the agent turn."""
    mock_event = MagicMock()
    mock_event.content = MagicMock()
    mock_event.content.parts = [MagicMock(text="Your preference is dark mode.", function_call=None)]
    mock_event.is_final_response.return_value = True

    async def mock_run_async(**kwargs):
        yield mock_event

    runner_with_memory._runner = MagicMock()
    runner_with_memory._runner.run_async = mock_run_async

    response = await runner_with_memory.run(
        user_id="user_123",
        session_id="sess_1",
        message="I prefer dark mode",
    )

    memory_service.capture.assert_awaited_once()
    call_kwargs = memory_service.capture.call_args.kwargs
    assert call_kwargs["user_id"] == "user_123"
    assert "I prefer dark mode" in call_kwargs["conversation_text"]
    assert "Your preference is dark mode." in call_kwargs["conversation_text"]


@pytest.mark.asyncio
async def test_run_without_memory(runner_without_memory):
    """Runner works fine without memory service."""
    mock_event = MagicMock()
    mock_event.content = MagicMock()
    mock_event.content.parts = [MagicMock(text="Hello!", function_call=None)]
    mock_event.is_final_response.return_value = True

    async def mock_run_async(**kwargs):
        yield mock_event

    runner_without_memory._runner = MagicMock()
    runner_without_memory._runner.run_async = mock_run_async

    response = await runner_without_memory.run(
        user_id="user_123",
        session_id="sess_1",
        message="Hello",
    )

    assert response.text == "Hello!"


@pytest.mark.asyncio
async def test_memory_failure_does_not_break_run(runner_with_memory, memory_service):
    """If memory operations fail, the agent turn still succeeds."""
    memory_service.recall.side_effect = Exception("Memory Bank unavailable")

    mock_event = MagicMock()
    mock_event.content = MagicMock()
    mock_event.content.parts = [MagicMock(text="Hello!", function_call=None)]
    mock_event.is_final_response.return_value = True

    async def mock_run_async(**kwargs):
        yield mock_event

    runner_with_memory._runner = MagicMock()
    runner_with_memory._runner.run_async = mock_run_async

    # Should not raise even though recall failed
    response = await runner_with_memory.run(
        user_id="user_123",
        session_id="sess_1",
        message="Hello",
    )

    assert response.text == "Hello!"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_runner_memory.py -v`
Expected: FAIL — `TypeError` because `AgentRunner.__init__` does not accept `memory_service`.

- [ ] **Step 3: Update AgentRunner with memory hooks**

Modify `src/gclaw/dispatch/runner.py`:

```python
"""Run agent turns via ADK Runner."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService
from google.genai import types

if TYPE_CHECKING:
    from gclaw.memory.service import MemoryService

logger = logging.getLogger(__name__)


@dataclass
class AgentResponse:
    """Response from a single agent turn."""

    text: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    is_final: bool = False


class AgentRunner:
    """Wraps ADK Runner for executing agent turns.

    When a MemoryService is provided:
    - Before each turn: auto-recall relevant memories
    - After each turn: auto-capture facts from the exchange (fire-and-forget)
    """

    def __init__(
        self,
        agent: LlmAgent,
        app_name: str,
        session_service: BaseSessionService,
        memory_service: MemoryService | None = None,
    ) -> None:
        self._agent = agent
        self._app_name = app_name
        self._session_service = session_service
        self._memory_service = memory_service
        self._runner = Runner(
            agent=agent,
            app_name=app_name,
            session_service=session_service,
        )

    async def run(
        self,
        user_id: str,
        session_id: str,
        message: str,
    ) -> AgentResponse:
        """Run a single turn: send message, collect response.

        Memory hooks:
        1. Auto-recall: retrieve relevant memories before the turn
        2. Execute the agent turn
        3. Auto-capture: extract facts from the exchange (fire-and-forget)
        """
        # 1. Auto-recall memories
        recalled_text = ""
        if self._memory_service is not None:
            try:
                memories = await self._memory_service.recall(
                    user_id=user_id,
                    query=message,
                )
                if memories:
                    recalled_text = self._memory_service.format_for_prompt(memories)
            except Exception:
                logger.warning(
                    "Memory recall failed for user %s, proceeding without memories",
                    user_id,
                    exc_info=True,
                )

        # Build the user message, optionally prepending recalled memories
        if recalled_text:
            full_message = (
                f"[Recalled memories]\n{recalled_text}\n\n"
                f"[User message]\n{message}"
            )
        else:
            full_message = message

        content = types.Content(
            role="user",
            parts=[types.Part(text=full_message)],
        )

        # 2. Execute the agent turn
        response = AgentResponse()

        async for event in self._runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=content,
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        response.text += part.text
                    if part.function_call:
                        response.tool_calls.append({
                            "name": part.function_call.name,
                            "args": dict(part.function_call.args or {}),
                        })

            if event.is_final_response():
                response.is_final = True

        # 3. Auto-capture memories (fire-and-forget)
        if self._memory_service is not None and response.text:
            try:
                conversation_text = f"User: {message}\nAgent: {response.text}"
                await self._memory_service.capture(
                    user_id=user_id,
                    conversation_text=conversation_text,
                )
            except Exception:
                logger.warning(
                    "Memory capture failed for user %s, continuing",
                    user_id,
                    exc_info=True,
                )

        return response
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_runner_memory.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Verify existing runner tests still pass**

Run: `pytest tests/test_dispatcher.py -v`
Expected: All existing tests PASS (backward compatible due to `memory_service=None` default).

- [ ] **Step 6: Commit**

```bash
git add src/gclaw/dispatch/runner.py tests/test_runner_memory.py
git commit -m "feat: add memory hooks to AgentRunner — auto-recall before turns, auto-capture after"
```

---

### Task 9: Integration — Update Heartbeat Context with Memories

**Files:**
- Modify: `src/gclaw/heartbeat/context.py`
- Create: `tests/test_heartbeat_memory.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_heartbeat_memory.py`:

```python
"""Tests for heartbeat context integration with memories."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock

from gclaw.models.memory import Memory
from gclaw.heartbeat.context import HeartbeatContextGatherer


@pytest.fixture
def board_service():
    svc = MagicMock()
    svc.get_all_tasks.return_value = []
    return svc


@pytest.fixture
def cron_service():
    svc = MagicMock()
    svc.list_all.return_value = []
    return svc


@pytest.fixture
def memory_service():
    svc = MagicMock()
    svc.recall = AsyncMock(return_value=[
        Memory(fact="User has a meeting at 3pm", topic="ROUTINES"),
        Memory(fact="User asked to be reminded about the report", topic="ACTION_ITEMS"),
    ])
    svc.format_for_prompt = MagicMock(
        return_value="- User has a meeting at 3pm\n- User asked to be reminded about the report"
    )
    return svc


@pytest.fixture
def gatherer_with_memory(board_service, cron_service, memory_service):
    return HeartbeatContextGatherer(
        board_service=board_service,
        cron_service=cron_service,
        memory_service=memory_service,
        user_id="user_123",
    )


@pytest.fixture
def gatherer_without_memory(board_service, cron_service):
    return HeartbeatContextGatherer(
        board_service=board_service,
        cron_service=cron_service,
    )


@pytest.mark.asyncio
async def test_gather_includes_memories(gatherer_with_memory, memory_service):
    context = await gatherer_with_memory.gather_async()

    assert len(context["memories"]) == 2
    assert context["memories"][0].fact == "User has a meeting at 3pm"
    memory_service.recall.assert_awaited_once()


@pytest.mark.asyncio
async def test_gather_message_includes_memories(gatherer_with_memory, memory_service):
    message = await gatherer_with_memory.gather_as_message_async()

    assert "Relevant Memories" in message
    assert "User has a meeting at 3pm" in message


def test_gather_without_memory(gatherer_without_memory):
    """Sync gather still works without memory service."""
    context = gatherer_without_memory.gather()

    assert context["memories"] == []


def test_gather_message_without_memory(gatherer_without_memory):
    """Sync gather_as_message still works without memory service."""
    message = gatherer_without_memory.gather_as_message()

    assert "Relevant Memories" not in message


@pytest.mark.asyncio
async def test_memory_failure_does_not_break_gather(gatherer_with_memory, memory_service):
    """If memory recall fails, gather should still succeed."""
    memory_service.recall.side_effect = Exception("Memory Bank unavailable")

    context = await gatherer_with_memory.gather_async()

    assert context["memories"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_heartbeat_memory.py -v`
Expected: FAIL — `TypeError` because `HeartbeatContextGatherer.__init__` does not accept `memory_service`.

- [ ] **Step 3: Update HeartbeatContextGatherer**

Modify `src/gclaw/heartbeat/context.py`:

```python
"""Context gatherer for the heartbeat consciousness loop.

Scans the board, crons, memories, and system state to build a context snapshot
that the orchestrator uses to decide what actions to take.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from gclaw.board.service import BoardService
from gclaw.cron.service import CronService
from gclaw.models.task import TaskStatus

if TYPE_CHECKING:
    from gclaw.memory.service import MemoryService

logger = logging.getLogger(__name__)


class HeartbeatContextGatherer:
    """Gathers world state for the orchestrator's heartbeat reasoning."""

    def __init__(
        self,
        board_service: BoardService,
        cron_service: CronService,
        memory_service: MemoryService | None = None,
        user_id: str | None = None,
    ) -> None:
        self._board = board_service
        self._crons = cron_service
        self._memory = memory_service
        self._user_id = user_id

    def gather(self) -> dict:
        """Gather full context snapshot for heartbeat reasoning (sync, no memories).

        Returns a dict with:
        - current_time: ISO timestamp
        - board_summary: task counts by status
        - failed_tasks: list of failed task summaries
        - pending_approvals: tasks needing user approval
        - stale_tasks: tasks stuck in progress (placeholder for time-based check)
        - cron_summary: overview of cron definitions
        - memories: empty list (use gather_async for memory-enriched context)
        """
        return self._gather_board_and_crons([])

    async def gather_async(self) -> dict:
        """Gather full context snapshot including memories from Memory Bank.

        Returns the same dict as gather() but with memories populated
        from Vertex AI Memory Bank if the memory service is available.
        """
        memories = []
        if self._memory is not None and self._user_id is not None:
            try:
                memories = await self._memory.recall(
                    user_id=self._user_id,
                    query="pending tasks, reminders, upcoming events, commitments",
                )
            except Exception:
                logger.warning(
                    "Memory recall failed during heartbeat gather, "
                    "proceeding without memories",
                    exc_info=True,
                )

        return self._gather_board_and_crons(memories)

    def _gather_board_and_crons(self, memories: list) -> dict:
        """Internal helper — gather board + cron state with provided memories."""
        now = datetime.now(timezone.utc)
        tasks = self._board.get_all_tasks()

        # Count tasks by status
        status_counts: dict[str, int] = {}
        for status in TaskStatus:
            status_counts[status.value] = 0
        for task in tasks:
            status_counts[task.status.value] += 1

        # Collect notable tasks
        failed_tasks = [
            {"id": t.id, "title": t.title, "assignee": t.assignee}
            for t in tasks
            if t.status == TaskStatus.FAILED
        ]
        pending_approvals = [
            {"id": t.id, "title": t.title, "assignee": t.assignee}
            for t in tasks
            if t.status == TaskStatus.NEEDS_APPROVAL
        ]

        # Stale detection placeholder — in future, compare updated_at to now
        stale_tasks: list[dict] = []

        # Cron summary
        crons = self._crons.list_all()

        return {
            "current_time": now.isoformat(),
            "board_summary": {
                "total_tasks": len(tasks),
                "backlog": status_counts.get("backlog", 0),
                "queued": status_counts.get("queued", 0),
                "in_progress": status_counts.get("in_progress", 0),
                "needs_approval": status_counts.get("needs_approval", 0),
                "done": status_counts.get("done", 0),
                "failed": status_counts.get("failed", 0),
            },
            "failed_tasks": failed_tasks,
            "pending_approvals": pending_approvals,
            "stale_tasks": stale_tasks,
            "cron_summary": {
                "total_crons": len(crons),
            },
            "memories": memories,
        }

    def gather_as_message(self) -> str:
        """Gather context and format as a message (sync, no memories)."""
        ctx = self.gather()
        return self._format_message(ctx)

    async def gather_as_message_async(self) -> str:
        """Gather context with memories and format as a message."""
        ctx = await self.gather_async()
        return self._format_message(ctx)

    def _format_message(self, ctx: dict) -> str:
        """Format a context dict into a message for the orchestrator."""
        parts = [
            "## Heartbeat Wake Cycle",
            "",
            f"**Time:** {ctx['current_time']}",
            "",
            "### Board Summary",
            f"- Total tasks: {ctx['board_summary']['total_tasks']}",
            f"- Backlog: {ctx['board_summary']['backlog']}",
            f"- Queued: {ctx['board_summary']['queued']}",
            f"- In progress: {ctx['board_summary']['in_progress']}",
            f"- Needs approval: {ctx['board_summary']['needs_approval']}",
            f"- Done: {ctx['board_summary']['done']}",
            f"- Failed: {ctx['board_summary']['failed']}",
        ]

        if ctx["failed_tasks"]:
            parts.append("")
            parts.append("### Failed Tasks (need retry or attention)")
            for ft in ctx["failed_tasks"]:
                parts.append(
                    f"- [{ft['id']}] {ft['title']} (assignee: {ft['assignee']})"
                )

        if ctx["pending_approvals"]:
            parts.append("")
            parts.append("### Pending Approvals")
            for pa in ctx["pending_approvals"]:
                parts.append(
                    f"- [{pa['id']}] {pa['title']} (assignee: {pa['assignee']})"
                )

        if ctx["stale_tasks"]:
            parts.append("")
            parts.append("### Stale Tasks (stuck too long)")
            for st in ctx["stale_tasks"]:
                parts.append(
                    f"- [{st['id']}] {st['title']} (assignee: {st['assignee']})"
                )

        parts.append("")
        parts.append(f"### Crons: {ctx['cron_summary']['total_crons']} defined")

        if ctx["memories"]:
            parts.append("")
            parts.append("### Relevant Memories")
            for m in ctx["memories"]:
                fact = m.fact if hasattr(m, "fact") else str(m)
                parts.append(f"- {fact}")

        parts.append("")
        parts.append(
            "Based on this context, decide what actions to take. Options:\n"
            "1. Create tasks on the board for agents to handle\n"
            "2. Retry failed tasks\n"
            "3. Notify the user about items needing attention\n"
            "4. Do nothing if all is quiet\n"
            "\n"
            "Respond with your reasoning and any actions you want to take."
        )

        return "\n".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_heartbeat_memory.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 5: Verify existing heartbeat tests still pass**

Run: `pytest tests/test_heartbeat_context.py -v`
Expected: All existing tests PASS (backward compatible due to `memory_service=None` default).

- [ ] **Step 6: Commit**

```bash
git add src/gclaw/heartbeat/context.py tests/test_heartbeat_memory.py
git commit -m "feat: integrate memories into heartbeat context with async gather and graceful fallback"
```

---

### Task 10: Full Verification + Settings Update + App Wiring

**Files:**
- Modify: `src/gclaw/settings.py`
- Modify: `src/gclaw/config/loader.py`
- Modify: `src/gclaw/api/app.py`

- [ ] **Step 1: Update Settings with memory and skill configuration**

Modify `src/gclaw/settings.py`:

```python
"""Application settings loaded from environment variables."""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    gcp_project_id: str = field(
        default_factory=lambda: os.environ["GCP_PROJECT_ID"]
    )
    gcp_location: str = field(
        default_factory=lambda: os.environ.get("GCP_LOCATION", "us-central1")
    )
    gemini_pro_model: str = field(
        default_factory=lambda: os.environ.get(
            "GEMINI_PRO_MODEL", "gemini-2.5-flash"
        )
    )
    gemini_flash_model: str = field(
        default_factory=lambda: os.environ.get(
            "GEMINI_FLASH_MODEL", "gemini-2.5-flash"
        )
    )
    firestore_database: str = field(
        default_factory=lambda: os.environ.get("FIRESTORE_DATABASE", "(default)")
    )
    config_dir: str = field(
        default_factory=lambda: os.environ.get(
            "GCLAW_CONFIG_DIR",
            os.path.join(os.path.dirname(__file__), "..", ".."),
        )
    )
    # Heartbeat settings
    heartbeat_session_id: str = field(
        default_factory=lambda: os.environ.get(
            "HEARTBEAT_SESSION_ID", "heartbeat"
        )
    )
    # Memory Bank settings
    memory_bank_id: str = field(
        default_factory=lambda: os.environ.get(
            "MEMORY_BANK_ID", "default"
        )
    )
    memory_enabled: bool = field(
        default_factory=lambda: os.environ.get(
            "MEMORY_ENABLED", "true"
        ).lower() == "true"
    )
    # Session settings
    session_compaction_threshold: int = field(
        default_factory=lambda: int(os.environ.get(
            "SESSION_COMPACTION_THRESHOLD", "50"
        ))
    )
    # Skills settings
    skills_dir: str = field(
        default_factory=lambda: os.environ.get(
            "GCLAW_SKILLS_DIR",
            os.path.join(os.path.dirname(__file__), "..", "..", "skills"),
        )
    )


def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 2: Update ConfigLoader to merge skill instructions**

Modify `src/gclaw/config/loader.py`:

```python
"""Load and merge soul/agent.md configuration files into system prompts."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gclaw.models.skill import Skill
    from gclaw.skill.loader import SkillLoader


class ConfigLoader:
    """Loads soul and agent definition files from the config directory.

    Directory structure expected:
        config_dir/
            soul/
                base.md
                workspace.md
                dev.md
                ...
            agents/
                orchestrator.md
                workspace-mgr.md
                ...
    """

    def __init__(
        self,
        config_dir: str,
        skill_loader: SkillLoader | None = None,
    ) -> None:
        self._config_dir = config_dir
        self._skill_loader = skill_loader

    def load_soul(self, base: str, overlay: str | None = None) -> str:
        base_path = os.path.join(self._config_dir, "soul", f"{base}.md")
        if not os.path.isfile(base_path):
            raise FileNotFoundError(f"Soul base not found: {base_path}")

        with open(base_path) as f:
            content = f.read()

        if overlay:
            overlay_path = os.path.join(
                self._config_dir, "soul", f"{overlay}.md"
            )
            if os.path.isfile(overlay_path):
                with open(overlay_path) as f:
                    content += "\n" + f.read()

        return content

    def load_agent(self, agent_name: str) -> str:
        path = os.path.join(self._config_dir, "agents", f"{agent_name}.md")
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Agent definition not found: {path}")

        with open(path) as f:
            return f.read()

    def build_system_prompt(
        self,
        agent_name: str,
        soul_base: str = "base",
        soul_overlay: str | None = None,
        memories: list[str] | None = None,
        skills: list[Skill] | None = None,
    ) -> str:
        parts: list[str] = []

        # Agent definition
        agent_def = self.load_agent(agent_name)
        parts.append(f"# Agent Role\n\n{agent_def}")

        # Soul
        soul = self.load_soul(soul_base, overlay=soul_overlay)
        parts.append(f"# Personality & User Context\n\n{soul}")

        # Injected memories
        if memories:
            formatted = "\n".join(f"- {m}" for m in memories)
            parts.append(
                f"# Relevant Memories\n\n{formatted}"
            )

        # Skill instructions
        if skills and self._skill_loader is not None:
            skills_prompt = self._skill_loader.build_skills_prompt(skills)
            if skills_prompt:
                parts.append(skills_prompt)

        return "\n\n---\n\n".join(parts)
```

- [ ] **Step 3: Update create_app for new services**

Modify `src/gclaw/api/app.py`:

```python
"""FastAPI app factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from gclaw.api.chat import init_chat_router
from gclaw.api.board_routes import init_board_router
from gclaw.api.cron_routes import init_cron_router
from gclaw.api.heartbeat_routes import init_heartbeat_router
from gclaw.board.service import BoardService
from gclaw.cron.service import CronService
from gclaw.dispatch.runner import AgentRunner


def create_app(
    board_service: BoardService,
    agent_runner: AgentRunner,
    cron_service: CronService | None = None,
    heartbeat_service: object | None = None,
    session_service: object | None = None,
    memory_service: object | None = None,
    skill_registry: object | None = None,
) -> FastAPI:
    app = FastAPI(title="GClaw", version="0.3.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(init_chat_router(agent_runner))
    app.include_router(init_board_router(board_service))

    if cron_service is not None:
        app.include_router(init_cron_router(cron_service))

    if heartbeat_service is not None:
        app.include_router(init_heartbeat_router(heartbeat_service))

    # Store services on app state for use by future route extensions
    app.state.session_service = session_service
    app.state.memory_service = memory_service
    app.state.skill_registry = skill_registry

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app
```

- [ ] **Step 4: Update .env.example**

Append to `.env.example`:

```
# Memory Bank
MEMORY_BANK_ID=default
MEMORY_ENABLED=true

# Sessions
SESSION_COMPACTION_THRESHOLD=50

# Skills
GCLAW_SKILLS_DIR=skills
```

- [ ] **Step 5: Run the full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: ALL tests pass — both new and existing.

Verify specific test files:
- `pytest tests/test_session_model.py -v` — 11 pass
- `pytest tests/test_session_repo.py -v` — 7 pass
- `pytest tests/test_session_service.py -v` — 11 pass
- `pytest tests/test_memory_client.py -v` — 9 pass
- `pytest tests/test_memory_service.py -v` — 10 pass
- `pytest tests/test_skill_model.py -v` — 8 pass
- `pytest tests/test_skill_registry.py -v` — 7 pass
- `pytest tests/test_skill_loader.py -v` — 7 pass
- `pytest tests/test_skill_discovery.py -v` — 6 pass
- `pytest tests/test_runner_memory.py -v` — 4 pass
- `pytest tests/test_heartbeat_memory.py -v` — 5 pass

- [ ] **Step 6: Verify backward compatibility**

Run: `pytest tests/test_api.py tests/test_dispatcher.py tests/test_heartbeat_context.py tests/test_heartbeat_service.py tests/test_config_loader.py -v`
Expected: All existing tests still pass — no breaking changes.

- [ ] **Step 7: Commit**

```bash
git add src/gclaw/settings.py src/gclaw/config/loader.py src/gclaw/api/app.py .env.example
git commit -m "feat: wire memory bank, session, and skill services into settings, config loader, and app factory"
```
