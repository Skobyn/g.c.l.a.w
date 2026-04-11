# GClaw Multi-User A2A + Onboarding (Plan 4c of 4)

> **STATUS: partial (2026-04-11).**
> **Done:** `models/connection.py`, `connection/` service scaffolding, `api/connection_routes.py`, cross-user task model in `models/cross_user_task.py`, onboarding route skeleton (`api/onboarding_routes.py`).
> **Left:** Connection permission-scoping + the conversational onboarding flow that generates initial soul profiles; frontend connection management view. A2A cross-user task creation exists in model form but isn't exercised end-to-end.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement cross-user A2A connections with permission-based shared scopes, cross-user task creation, a conversational onboarding flow that generates the user's initial soul profile, and frontend views for managing connections and completing onboarding.

**Architecture:** Connections are bilateral Firestore records stored in each user's `connections/` subcollection. A `ConnectionService` manages the full lifecycle (request, accept, reject, revoke) and enforces permission levels (read, write, task, full). Cross-user task creation flows through the connection service's permission check before delegating to the target user's `BoardRepo`. The onboarding flow is conversational -- the orchestrator agent conducts the interview via the existing chat infrastructure, and an `OnboardingService` tracks progress, stores responses, and triggers soul file generation by sending the collected interview through the orchestrator. The frontend adds a Connections page for managing A2A relationships and an onboarding wizard that gates new users into the interview conversation before normal operation.

**Tech Stack:**
- Backend: Python 3.10, FastAPI, Pydantic v2, firebase-admin (Firestore), google-genai
- Frontend: Next.js 14+ App Router, TypeScript (strict), Tailwind CSS, Firebase JS SDK
- Testing: pytest + mocks (backend), vitest + React Testing Library (frontend)

**Builds on Plans 1-4b:**
- `create_app` factory in `api/app.py` with service injection and auth middleware
- `AgentRunner`, `BoardService`, `MemoryService`, `ConfigLoader`
- `BoardRepo` at `users/{userId}/board/{taskId}` with `create()`, `get()`, `list_all()`
- `MemoryService` with `recall()`, `capture()`, `generate_memories()`, `format_for_prompt()`
- `MemoryScope(user_id, agent)` model -- will be extended with `shared_channel`
- Auth middleware (`FirebaseAuthMiddleware`) and `get_current_user_id` dependency
- `ApiClient` in `web/src/lib/api-client.ts` with token injection
- `AuthProvider` / `useAuth()` context, `AuthGuard` component
- All five web views (Chat, Board, Agents, Skills/Crons, Memory) with sidebar navigation
- Existing types in `web/src/types/index.ts`

---

## File Structure

```
gclaw/
├── src/
│   └── gclaw/
│       ├── models/
│       │   ├── connection.py                          # NEW: Connection + Permission models
│       │   └── onboarding.py                          # NEW: OnboardingState model
│       ├── firestore/
│       │   └── connection_repo.py                     # NEW: Firestore CRUD for connections
│       ├── connection/
│       │   ├── __init__.py                            # NEW
│       │   └── service.py                             # NEW: ConnectionService (request/accept/reject/revoke)
│       ├── onboarding/
│       │   ├── __init__.py                            # NEW
│       │   └── service.py                             # NEW: OnboardingService (interview flow, soul gen)
│       ├── memory/
│       │   └── service.py                             # MODIFY: add shared_channel recall support
│       ├── models/
│       │   └── memory.py                              # MODIFY: add shared_channel to MemoryScope
│       ├── api/
│       │   ├── app.py                                 # MODIFY: register connection + onboarding routers
│       │   ├── connection_routes.py                   # NEW: A2A connection endpoints
│       │   └── onboarding_routes.py                   # NEW: Onboarding endpoints
├── tests/
│   ├── test_connection_model.py                       # NEW
│   ├── test_connection_service.py                     # NEW
│   ├── test_connection_routes.py                      # NEW
│   ├── test_cross_user_task.py                        # NEW
│   ├── test_onboarding_service.py                     # NEW
│   └── test_onboarding_routes.py                      # NEW
├── web/
│   ├── src/
│   │   ├── app/
│   │   │   ├── connections/
│   │   │   │   └── page.tsx                           # NEW: Connections management view
│   │   │   └── onboarding/
│   │   │       └── page.tsx                           # NEW: Onboarding wizard page
│   │   ├── lib/
│   │   │   └── api-client.ts                          # MODIFY: add connection + onboarding methods
│   │   ├── components/
│   │   │   ├── connections/
│   │   │   │   ├── connection-list.tsx                 # NEW: Active connections list
│   │   │   │   ├── connection-request-form.tsx         # NEW: Send connection request
│   │   │   │   ├── incoming-requests.tsx               # NEW: Accept/reject incoming
│   │   │   │   └── permission-editor.tsx               # NEW: Edit permissions per connection
│   │   │   └── onboarding/
│   │   │       ├── onboarding-wizard.tsx               # NEW: Multi-step onboarding wrapper
│   │   │       └── onboarding-chat.tsx                 # NEW: Conversational interview UI
│   │   └── types/
│   │       └── index.ts                               # MODIFY: add Connection + Onboarding types
│   ├── __tests__/
│   │   ├── connections-view.test.tsx                   # NEW
│   │   └── onboarding-wizard.test.tsx                  # NEW
```

---

### Task 1: Connection Model (Pydantic + Firestore)

**Files:**
- Create: `src/gclaw/models/connection.py`
- Create: `src/gclaw/firestore/connection_repo.py`
- Create: `tests/test_connection_model.py`

- [ ] **Step 1: Write failing tests for the connection model**

Create `tests/test_connection_model.py`:

```python
"""Tests for connection models."""

from __future__ import annotations

import pytest
from gclaw.models.connection import (
    Connection,
    ConnectionPermission,
    ConnectionStatus,
)


def test_connection_creation_defaults():
    """Connection should have sensible defaults."""
    conn = Connection(
        id="conn_abc123",
        from_user_id="user_a",
        to_user_id="user_b",
    )
    assert conn.status == ConnectionStatus.PENDING
    assert conn.permission == ConnectionPermission.READ
    assert conn.from_user_id == "user_a"
    assert conn.to_user_id == "user_b"
    assert conn.shared_channel == ""


def test_connection_permission_levels():
    """All four permission levels should be valid."""
    for level in ("read", "write", "task", "full"):
        perm = ConnectionPermission(level)
        assert perm.value == level


def test_connection_status_transitions():
    """Status should support pending, active, rejected, revoked."""
    for status in ("pending", "active", "rejected", "revoked"):
        s = ConnectionStatus(status)
        assert s.value == status


def test_connection_to_firestore_dict():
    """Should serialize to dict without id field."""
    conn = Connection(
        id="conn_abc",
        from_user_id="user_a",
        to_user_id="user_b",
        permission=ConnectionPermission.TASK,
        shared_channel="user_a__user_b",
    )
    d = conn.to_firestore_dict()
    assert "id" not in d
    assert d["from_user_id"] == "user_a"
    assert d["permission"] == "task"
    assert d["shared_channel"] == "user_a__user_b"


def test_connection_from_firestore_dict():
    """Should deserialize from Firestore doc."""
    data = {
        "from_user_id": "user_a",
        "to_user_id": "user_b",
        "status": "active",
        "permission": "write",
        "shared_channel": "user_a__user_b",
    }
    conn = Connection.from_firestore_dict("conn_xyz", data)
    assert conn.id == "conn_xyz"
    assert conn.status == ConnectionStatus.ACTIVE
    assert conn.permission == ConnectionPermission.WRITE


def test_connection_has_permission():
    """Permission hierarchy: full > task > write > read."""
    conn = Connection(
        id="c1",
        from_user_id="a",
        to_user_id="b",
        permission=ConnectionPermission.TASK,
    )
    assert conn.has_permission(ConnectionPermission.READ) is True
    assert conn.has_permission(ConnectionPermission.WRITE) is True
    assert conn.has_permission(ConnectionPermission.TASK) is True
    assert conn.has_permission(ConnectionPermission.FULL) is False
```

- [ ] **Step 2: Implement the connection model**

Create `src/gclaw/models/connection.py`:

```python
"""Connection models for cross-user A2A protocol."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing_extensions import Self

from pydantic import BaseModel, Field


class ConnectionStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    REJECTED = "rejected"
    REVOKED = "revoked"


class ConnectionPermission(str, Enum):
    """Permission levels — hierarchical: full > task > write > read."""

    READ = "read"
    WRITE = "write"
    TASK = "task"
    FULL = "full"


# Permission hierarchy for comparison
_PERMISSION_RANK: dict[ConnectionPermission, int] = {
    ConnectionPermission.READ: 0,
    ConnectionPermission.WRITE: 1,
    ConnectionPermission.TASK: 2,
    ConnectionPermission.FULL: 3,
}


class Connection(BaseModel):
    """A cross-user connection record.

    Bilateral — both users have a matching record in their
    ``connections/`` subcollection.
    """

    id: str = Field(
        default_factory=lambda: f"conn_{uuid.uuid4().hex[:12]}"
    )
    from_user_id: str
    to_user_id: str
    status: ConnectionStatus = ConnectionStatus.PENDING
    permission: ConnectionPermission = ConnectionPermission.READ
    shared_channel: str = ""
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def has_permission(self, required: ConnectionPermission) -> bool:
        """Check if this connection meets the required permission level."""
        return _PERMISSION_RANK[self.permission] >= _PERMISSION_RANK[required]

    def to_firestore_dict(self) -> dict:
        d = self.model_dump(mode="json")
        d.pop("id")
        return d

    @classmethod
    def from_firestore_dict(cls, doc_id: str, data: dict) -> Self:
        return cls(id=doc_id, **data)
```

- [ ] **Step 3: Implement the connection Firestore repository**

Create `src/gclaw/firestore/connection_repo.py`:

```python
"""Connection CRUD operations on Firestore.

Collection path: users/{userId}/connections/{connectionId}
"""

from __future__ import annotations

from google.cloud.firestore import Client as FirestoreClient

from gclaw.models.connection import Connection, ConnectionStatus


class ConnectionRepo:
    """Synchronous Firestore repository for user connections."""

    def __init__(self, db: FirestoreClient, user_id: str) -> None:
        self._db = db
        self._user_id = user_id

    def _collection_ref(self):
        return (
            self._db.collection("users")
            .document(self._user_id)
            .collection("connections")
        )

    def create(self, connection: Connection) -> Connection:
        doc_ref = self._collection_ref().document(connection.id)
        doc_ref.set(connection.to_firestore_dict())
        return connection

    def get(self, connection_id: str) -> Connection | None:
        doc = self._collection_ref().document(connection_id).get()
        if not doc.exists:
            return None
        return Connection.from_firestore_dict(doc.id, doc.to_dict())

    def update(self, connection: Connection) -> Connection:
        doc_ref = self._collection_ref().document(connection.id)
        doc_ref.set(connection.to_firestore_dict())
        return connection

    def delete(self, connection_id: str) -> None:
        self._collection_ref().document(connection_id).delete()

    def list_by_status(self, status: ConnectionStatus) -> list[Connection]:
        docs = (
            self._collection_ref()
            .where("status", "==", status.value)
            .stream()
        )
        return [
            Connection.from_firestore_dict(doc.id, doc.to_dict())
            for doc in docs
        ]

    def list_active(self) -> list[Connection]:
        return self.list_by_status(ConnectionStatus.ACTIVE)

    def list_pending_incoming(self) -> list[Connection]:
        """List pending requests where this user is the recipient."""
        docs = (
            self._collection_ref()
            .where("status", "==", ConnectionStatus.PENDING.value)
            .where("to_user_id", "==", self._user_id)
            .stream()
        )
        return [
            Connection.from_firestore_dict(doc.id, doc.to_dict())
            for doc in docs
        ]

    def find_by_peer(self, peer_user_id: str) -> Connection | None:
        """Find an active or pending connection with a specific user."""
        docs = list(
            self._collection_ref()
            .where("status", "in", [
                ConnectionStatus.PENDING.value,
                ConnectionStatus.ACTIVE.value,
            ])
            .stream()
        )
        for doc in docs:
            data = doc.to_dict()
            other = (
                data.get("to_user_id")
                if data.get("from_user_id") == self._user_id
                else data.get("from_user_id")
            )
            if other == peer_user_id:
                return Connection.from_firestore_dict(doc.id, data)
        return None
```

- [ ] **Step 4: Run tests, verify all pass**

```bash
cd /mnt/c/Dev/GClaw && python -m pytest tests/test_connection_model.py -v
```

---

### Task 2: Connection Service (Request/Accept/Reject/Revoke with Permission Enforcement)

**Files:**
- Create: `src/gclaw/connection/__init__.py`
- Create: `src/gclaw/connection/service.py`
- Modify: `src/gclaw/models/memory.py` (add `shared_channel` to `MemoryScope`)
- Modify: `src/gclaw/memory/service.py` (add shared channel recall)
- Create: `tests/test_connection_service.py`

- [ ] **Step 1: Write failing tests for the connection service**

Create `tests/test_connection_service.py`:

```python
"""Tests for the ConnectionService."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from gclaw.connection.service import ConnectionService
from gclaw.models.connection import (
    Connection,
    ConnectionPermission,
    ConnectionStatus,
)


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def service(mock_db):
    return ConnectionService(db=mock_db)


def _make_pending_conn(
    from_user: str = "user_a",
    to_user: str = "user_b",
) -> Connection:
    return Connection(
        id="conn_test",
        from_user_id=from_user,
        to_user_id=to_user,
        status=ConnectionStatus.PENDING,
        permission=ConnectionPermission.READ,
    )


class TestRequestConnection:
    def test_creates_bilateral_records(self, service, mock_db):
        """Request should create a record in both users' subcollections."""
        conn = service.request_connection(
            from_user_id="user_a",
            to_user_id="user_b",
            permission=ConnectionPermission.WRITE,
        )
        assert conn.from_user_id == "user_a"
        assert conn.to_user_id == "user_b"
        assert conn.status == ConnectionStatus.PENDING
        assert conn.permission == ConnectionPermission.WRITE
        # Both repos should have had create() called
        assert mock_db.collection.call_count >= 2

    def test_rejects_self_connection(self, service):
        """Cannot connect to yourself."""
        with pytest.raises(ValueError, match="Cannot connect to yourself"):
            service.request_connection(
                from_user_id="user_a",
                to_user_id="user_a",
            )


class TestAcceptConnection:
    def test_accept_sets_active_and_creates_shared_channel(
        self, service, mock_db
    ):
        """Accept should set both records to active with shared_channel."""
        pending = _make_pending_conn()
        # Mock the repo to return the pending connection
        service._get_repo = MagicMock()
        repo_mock = MagicMock()
        repo_mock.get.return_value = pending
        service._get_repo.return_value = repo_mock

        result = service.accept_connection(
            user_id="user_b",
            connection_id="conn_test",
        )
        assert result.status == ConnectionStatus.ACTIVE
        assert result.shared_channel != ""

    def test_accept_rejects_if_not_recipient(self, service):
        """Only the recipient can accept."""
        pending = _make_pending_conn()
        service._get_repo = MagicMock()
        repo_mock = MagicMock()
        repo_mock.get.return_value = pending
        service._get_repo.return_value = repo_mock

        with pytest.raises(
            ValueError, match="Only the recipient can accept"
        ):
            service.accept_connection(
                user_id="user_a",  # sender, not recipient
                connection_id="conn_test",
            )


class TestRejectConnection:
    def test_reject_sets_rejected_status(self, service):
        """Reject should set status to rejected on both records."""
        pending = _make_pending_conn()
        service._get_repo = MagicMock()
        repo_mock = MagicMock()
        repo_mock.get.return_value = pending
        service._get_repo.return_value = repo_mock

        result = service.reject_connection(
            user_id="user_b",
            connection_id="conn_test",
        )
        assert result.status == ConnectionStatus.REJECTED


class TestRevokeConnection:
    def test_revoke_sets_revoked_status(self, service):
        """Either user can revoke an active connection."""
        active = Connection(
            id="conn_test",
            from_user_id="user_a",
            to_user_id="user_b",
            status=ConnectionStatus.ACTIVE,
            shared_channel="user_a__user_b",
        )
        service._get_repo = MagicMock()
        repo_mock = MagicMock()
        repo_mock.get.return_value = active
        service._get_repo.return_value = repo_mock

        result = service.revoke_connection(
            user_id="user_a",
            connection_id="conn_test",
        )
        assert result.status == ConnectionStatus.REVOKED


class TestPermissionEnforcement:
    def test_check_permission_passes(self, service):
        """Should not raise when permission is sufficient."""
        active = Connection(
            id="c1",
            from_user_id="a",
            to_user_id="b",
            status=ConnectionStatus.ACTIVE,
            permission=ConnectionPermission.TASK,
        )
        service._get_repo = MagicMock()
        repo_mock = MagicMock()
        repo_mock.get.return_value = active
        service._get_repo.return_value = repo_mock

        # Should not raise
        service.check_permission(
            user_id="a",
            connection_id="c1",
            required=ConnectionPermission.WRITE,
        )

    def test_check_permission_fails(self, service):
        """Should raise when permission is insufficient."""
        active = Connection(
            id="c1",
            from_user_id="a",
            to_user_id="b",
            status=ConnectionStatus.ACTIVE,
            permission=ConnectionPermission.READ,
        )
        service._get_repo = MagicMock()
        repo_mock = MagicMock()
        repo_mock.get.return_value = active
        service._get_repo.return_value = repo_mock

        with pytest.raises(PermissionError):
            service.check_permission(
                user_id="a",
                connection_id="c1",
                required=ConnectionPermission.WRITE,
            )
```

- [ ] **Step 2: Extend MemoryScope with shared_channel**

Modify `src/gclaw/models/memory.py` -- add `shared_channel` field to `MemoryScope`:

```python
class MemoryScope(BaseModel):
    """Scope for memory operations.

    - user_id only: user-scoped (shared across all agents)
    - user_id + agent: agent-scoped (domain-specific per agent)
    - shared_channel: cross-user shared scope (consent-based)
    """

    user_id: str
    agent: str | None = None
    shared_channel: str | None = None
```

- [ ] **Step 3: Add shared channel recall to MemoryService**

Modify `src/gclaw/memory/service.py` -- add a `recall_shared` method after the existing `recall` method:

```python
async def recall_shared(
    self,
    shared_channel: str,
    query: str,
    top_k: int = 10,
) -> list[Memory]:
    """Retrieve memories from a shared cross-user channel.

    Args:
        shared_channel: The shared channel identifier (e.g. "userA__userB").
        query: Natural language query.
        top_k: Max memories to return.

    Returns:
        List of relevant Memory objects from the shared scope.
    """
    scope = MemoryScope(
        user_id="",  # Not user-specific
        shared_channel=shared_channel,
    )
    return await self._client.retrieve_memories(
        scope=scope, query=query, top_k=top_k,
    )
```

- [ ] **Step 4: Implement the ConnectionService**

Create `src/gclaw/connection/__init__.py` (empty).

Create `src/gclaw/connection/service.py`:

```python
"""Connection service — cross-user A2A connection lifecycle."""

from __future__ import annotations

from datetime import datetime, timezone

from google.cloud.firestore import Client as FirestoreClient

from gclaw.firestore.connection_repo import ConnectionRepo
from gclaw.models.connection import (
    Connection,
    ConnectionPermission,
    ConnectionStatus,
)


def _make_shared_channel(user_a: str, user_b: str) -> str:
    """Deterministic shared channel name (alphabetical order)."""
    parts = sorted([user_a, user_b])
    return f"{parts[0]}__{parts[1]}"


class ConnectionService:
    """Business logic for cross-user A2A connections.

    Connections are bilateral — both users hold a matching record
    in their ``users/{userId}/connections/`` subcollection.
    """

    def __init__(self, db: FirestoreClient) -> None:
        self._db = db

    def _get_repo(self, user_id: str) -> ConnectionRepo:
        return ConnectionRepo(self._db, user_id)

    def request_connection(
        self,
        from_user_id: str,
        to_user_id: str,
        permission: ConnectionPermission = ConnectionPermission.READ,
    ) -> Connection:
        """Send a connection request from one user to another.

        Creates a PENDING record in both users' subcollections.

        Raises:
            ValueError: If connecting to self or duplicate request.
        """
        if from_user_id == to_user_id:
            raise ValueError("Cannot connect to yourself")

        # Check for existing connection
        from_repo = self._get_repo(from_user_id)
        existing = from_repo.find_by_peer(to_user_id)
        if existing is not None:
            raise ValueError(
                f"Connection already exists with status: {existing.status}"
            )

        conn = Connection(
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            status=ConnectionStatus.PENDING,
            permission=permission,
        )

        # Write to both users' subcollections (same id for correlation)
        from_repo.create(conn)
        to_repo = self._get_repo(to_user_id)
        to_repo.create(conn)

        return conn

    def accept_connection(
        self,
        user_id: str,
        connection_id: str,
    ) -> Connection:
        """Accept a pending connection request.

        Only the recipient (to_user_id) can accept.
        Sets status to ACTIVE and creates a shared channel.

        Raises:
            ValueError: If not found, not recipient, or not pending.
        """
        repo = self._get_repo(user_id)
        conn = repo.get(connection_id)
        if conn is None:
            raise ValueError(f"Connection {connection_id} not found")
        if conn.to_user_id != user_id:
            raise ValueError("Only the recipient can accept")
        if conn.status != ConnectionStatus.PENDING:
            raise ValueError(f"Cannot accept connection in status: {conn.status}")

        shared_channel = _make_shared_channel(
            conn.from_user_id, conn.to_user_id
        )
        now = datetime.now(timezone.utc)

        updated = conn.model_copy(update={
            "status": ConnectionStatus.ACTIVE,
            "shared_channel": shared_channel,
            "updated_at": now,
        })

        # Update both users' records
        repo.update(updated)
        peer_repo = self._get_repo(conn.from_user_id)
        peer_repo.update(updated)

        return updated

    def reject_connection(
        self,
        user_id: str,
        connection_id: str,
    ) -> Connection:
        """Reject a pending connection request.

        Only the recipient can reject.

        Raises:
            ValueError: If not found, not recipient, or not pending.
        """
        repo = self._get_repo(user_id)
        conn = repo.get(connection_id)
        if conn is None:
            raise ValueError(f"Connection {connection_id} not found")
        if conn.to_user_id != user_id:
            raise ValueError("Only the recipient can reject")
        if conn.status != ConnectionStatus.PENDING:
            raise ValueError(f"Cannot reject connection in status: {conn.status}")

        now = datetime.now(timezone.utc)
        updated = conn.model_copy(update={
            "status": ConnectionStatus.REJECTED,
            "updated_at": now,
        })

        repo.update(updated)
        peer_repo = self._get_repo(conn.from_user_id)
        peer_repo.update(updated)

        return updated

    def revoke_connection(
        self,
        user_id: str,
        connection_id: str,
    ) -> Connection:
        """Revoke an active connection. Either user can revoke.

        Raises:
            ValueError: If not found or not active.
        """
        repo = self._get_repo(user_id)
        conn = repo.get(connection_id)
        if conn is None:
            raise ValueError(f"Connection {connection_id} not found")
        if conn.status != ConnectionStatus.ACTIVE:
            raise ValueError(f"Cannot revoke connection in status: {conn.status}")
        if user_id not in (conn.from_user_id, conn.to_user_id):
            raise ValueError("Not a party to this connection")

        now = datetime.now(timezone.utc)
        updated = conn.model_copy(update={
            "status": ConnectionStatus.REVOKED,
            "shared_channel": "",
            "updated_at": now,
        })

        repo.update(updated)
        peer_id = (
            conn.to_user_id
            if conn.from_user_id == user_id
            else conn.from_user_id
        )
        peer_repo = self._get_repo(peer_id)
        peer_repo.update(updated)

        return updated

    def check_permission(
        self,
        user_id: str,
        connection_id: str,
        required: ConnectionPermission,
    ) -> Connection:
        """Verify a connection is active and has sufficient permission.

        Returns the connection if valid.

        Raises:
            ValueError: If connection not found or not active.
            PermissionError: If permission is insufficient.
        """
        repo = self._get_repo(user_id)
        conn = repo.get(connection_id)
        if conn is None:
            raise ValueError(f"Connection {connection_id} not found")
        if conn.status != ConnectionStatus.ACTIVE:
            raise ValueError("Connection is not active")
        if not conn.has_permission(required):
            raise PermissionError(
                f"Connection permission '{conn.permission.value}' "
                f"is insufficient — requires '{required.value}'"
            )
        return conn

    def list_connections(
        self,
        user_id: str,
        status: ConnectionStatus | None = None,
    ) -> list[Connection]:
        """List connections for a user, optionally filtered by status."""
        repo = self._get_repo(user_id)
        if status is not None:
            return repo.list_by_status(status)
        return repo.list_active()

    def list_pending_incoming(self, user_id: str) -> list[Connection]:
        """List pending incoming connection requests."""
        repo = self._get_repo(user_id)
        return repo.list_pending_incoming()
```

- [ ] **Step 5: Run tests, verify all pass**

```bash
cd /mnt/c/Dev/GClaw && python -m pytest tests/test_connection_service.py -v
```

---

### Task 3: A2A API Endpoints

**Files:**
- Create: `src/gclaw/api/connection_routes.py`
- Modify: `src/gclaw/api/app.py`
- Create: `tests/test_connection_routes.py`

- [ ] **Step 1: Write failing tests for the connection endpoints**

Create `tests/test_connection_routes.py`:

```python
"""Tests for connection API routes."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gclaw.api.connection_routes import init_connection_router
from gclaw.models.connection import (
    Connection,
    ConnectionPermission,
    ConnectionStatus,
)


@pytest.fixture
def mock_connection_service():
    return MagicMock()


@pytest.fixture
def app(mock_connection_service):
    app = FastAPI()
    app.include_router(init_connection_router(mock_connection_service))
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture(autouse=True)
def mock_auth():
    with patch(
        "gclaw.api.connection_routes.get_current_user_id",
        return_value="test_user",
    ):
        yield


class TestRequestEndpoint:
    def test_request_connection(self, client, mock_connection_service):
        conn = Connection(
            id="conn_123",
            from_user_id="test_user",
            to_user_id="other_user",
            status=ConnectionStatus.PENDING,
        )
        mock_connection_service.request_connection.return_value = conn

        resp = client.post("/connections/request", json={
            "to_user_id": "other_user",
            "permission": "read",
        })
        assert resp.status_code == 200
        assert resp.json()["id"] == "conn_123"
        assert resp.json()["status"] == "pending"

    def test_request_self_returns_400(self, client, mock_connection_service):
        mock_connection_service.request_connection.side_effect = ValueError(
            "Cannot connect to yourself"
        )
        resp = client.post("/connections/request", json={
            "to_user_id": "test_user",
            "permission": "read",
        })
        assert resp.status_code == 400


class TestAcceptEndpoint:
    def test_accept_connection(self, client, mock_connection_service):
        conn = Connection(
            id="conn_123",
            from_user_id="other",
            to_user_id="test_user",
            status=ConnectionStatus.ACTIVE,
            shared_channel="other__test_user",
        )
        mock_connection_service.accept_connection.return_value = conn

        resp = client.post("/connections/conn_123/accept")
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"


class TestListEndpoints:
    def test_list_active_connections(self, client, mock_connection_service):
        mock_connection_service.list_connections.return_value = []
        resp = client.get("/connections")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_pending_incoming(self, client, mock_connection_service):
        mock_connection_service.list_pending_incoming.return_value = []
        resp = client.get("/connections/incoming")
        assert resp.status_code == 200
        assert resp.json() == []


class TestRevokeEndpoint:
    def test_revoke_connection(self, client, mock_connection_service):
        conn = Connection(
            id="conn_123",
            from_user_id="test_user",
            to_user_id="other",
            status=ConnectionStatus.REVOKED,
        )
        mock_connection_service.revoke_connection.return_value = conn

        resp = client.post("/connections/conn_123/revoke")
        assert resp.status_code == 200
        assert resp.json()["status"] == "revoked"
```

- [ ] **Step 2: Implement the connection routes**

Create `src/gclaw/api/connection_routes.py`:

```python
"""API routes for cross-user A2A connections."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from gclaw.auth.dependencies import get_current_user_id
from gclaw.connection.service import ConnectionService
from gclaw.models.connection import ConnectionPermission


class ConnectionRequest(BaseModel):
    to_user_id: str
    permission: str = "read"


class UpdatePermissionRequest(BaseModel):
    permission: str


def init_connection_router(
    connection_service: ConnectionService,
) -> APIRouter:
    router = APIRouter(prefix="/connections", tags=["connections"])

    @router.post("/request")
    def request_connection(
        body: ConnectionRequest,
        user_id: str = Depends(get_current_user_id),
    ):
        try:
            conn = connection_service.request_connection(
                from_user_id=user_id,
                to_user_id=body.to_user_id,
                permission=ConnectionPermission(body.permission),
            )
            return conn.model_dump(mode="json")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/{connection_id}/accept")
    def accept_connection(
        connection_id: str,
        user_id: str = Depends(get_current_user_id),
    ):
        try:
            conn = connection_service.accept_connection(
                user_id=user_id,
                connection_id=connection_id,
            )
            return conn.model_dump(mode="json")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/{connection_id}/reject")
    def reject_connection(
        connection_id: str,
        user_id: str = Depends(get_current_user_id),
    ):
        try:
            conn = connection_service.reject_connection(
                user_id=user_id,
                connection_id=connection_id,
            )
            return conn.model_dump(mode="json")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/{connection_id}/revoke")
    def revoke_connection(
        connection_id: str,
        user_id: str = Depends(get_current_user_id),
    ):
        try:
            conn = connection_service.revoke_connection(
                user_id=user_id,
                connection_id=connection_id,
            )
            return conn.model_dump(mode="json")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/{connection_id}/permission")
    def update_permission(
        connection_id: str,
        body: UpdatePermissionRequest,
        user_id: str = Depends(get_current_user_id),
    ):
        """Update the permission level on an active connection."""
        try:
            conn = connection_service.check_permission(
                user_id=user_id,
                connection_id=connection_id,
                required=ConnectionPermission.READ,
            )
            updated = conn.model_copy(update={
                "permission": ConnectionPermission(body.permission),
            })
            # Update via service (both records)
            from gclaw.firestore.connection_repo import ConnectionRepo
            repo = ConnectionRepo(connection_service._db, user_id)
            repo.update(updated)
            peer_id = (
                conn.to_user_id
                if conn.from_user_id == user_id
                else conn.from_user_id
            )
            peer_repo = ConnectionRepo(connection_service._db, peer_id)
            peer_repo.update(updated)
            return updated.model_dump(mode="json")
        except (ValueError, PermissionError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.get("")
    def list_connections(
        user_id: str = Depends(get_current_user_id),
    ):
        conns = connection_service.list_connections(user_id=user_id)
        return [c.model_dump(mode="json") for c in conns]

    @router.get("/incoming")
    def list_incoming(
        user_id: str = Depends(get_current_user_id),
    ):
        conns = connection_service.list_pending_incoming(user_id=user_id)
        return [c.model_dump(mode="json") for c in conns]

    return router
```

- [ ] **Step 3: Register the connection router in the app factory**

Modify `src/gclaw/api/app.py` -- add the import and router registration:

Add import at the top:

```python
from gclaw.api.connection_routes import init_connection_router
from gclaw.connection.service import ConnectionService
```

Add `connection_service: ConnectionService | None = None` parameter to `create_app`.

Add after the admin router registration block:

```python
if connection_service is not None:
    app.include_router(init_connection_router(connection_service))

# Store on app state
app.state.connection_service = connection_service
```

- [ ] **Step 4: Run tests, verify all pass**

```bash
cd /mnt/c/Dev/GClaw && python -m pytest tests/test_connection_routes.py -v
```

---

### Task 4: Cross-User Task Creation

**Files:**
- Modify: `src/gclaw/connection/service.py` (add `create_task_for_peer`)
- Create: `tests/test_cross_user_task.py`

- [ ] **Step 1: Write failing tests for cross-user task creation**

Create `tests/test_cross_user_task.py`:

```python
"""Tests for cross-user task creation via A2A connections."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from gclaw.connection.service import ConnectionService
from gclaw.models.connection import (
    Connection,
    ConnectionPermission,
    ConnectionStatus,
)
from gclaw.models.task import BoardTask, TaskStatus


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def mock_board_repo_factory():
    """Factory that returns a mock BoardRepo for any user_id."""
    repos = {}

    def factory(user_id: str):
        if user_id not in repos:
            repo = MagicMock()
            repo.create.side_effect = lambda task: task
            repos[user_id] = repo
        return repos[user_id]

    return factory


@pytest.fixture
def service(mock_db, mock_board_repo_factory):
    return ConnectionService(
        db=mock_db,
        board_repo_factory=mock_board_repo_factory,
    )


def _active_conn_with_task_permission() -> Connection:
    return Connection(
        id="conn_test",
        from_user_id="user_a",
        to_user_id="user_b",
        status=ConnectionStatus.ACTIVE,
        permission=ConnectionPermission.TASK,
        shared_channel="user_a__user_b",
    )


class TestCreateTaskForPeer:
    def test_creates_task_on_peer_board(
        self, service, mock_board_repo_factory
    ):
        """With task permission, should create task on peer's board."""
        conn = _active_conn_with_task_permission()
        service._get_repo = MagicMock()
        repo_mock = MagicMock()
        repo_mock.get.return_value = conn
        service._get_repo.return_value = repo_mock

        task = service.create_task_for_peer(
            user_id="user_a",
            connection_id="conn_test",
            title="Review my PR",
            assignee="orchestrator",
            description="PR #42 needs review",
        )

        assert isinstance(task, BoardTask)
        assert task.title == "Review my PR"
        assert task.source.origin == "user_a"
        # Verify it was created on user_b's board
        peer_repo = mock_board_repo_factory("user_b")
        peer_repo.create.assert_called_once()

    def test_fails_without_task_permission(self, service):
        """With only read permission, task creation should be denied."""
        conn = Connection(
            id="conn_test",
            from_user_id="user_a",
            to_user_id="user_b",
            status=ConnectionStatus.ACTIVE,
            permission=ConnectionPermission.READ,
        )
        service._get_repo = MagicMock()
        repo_mock = MagicMock()
        repo_mock.get.return_value = conn
        service._get_repo.return_value = repo_mock

        with pytest.raises(PermissionError):
            service.create_task_for_peer(
                user_id="user_a",
                connection_id="conn_test",
                title="Review my PR",
                assignee="orchestrator",
            )

    def test_fails_on_inactive_connection(self, service):
        """Cannot create tasks on revoked connections."""
        conn = Connection(
            id="conn_test",
            from_user_id="user_a",
            to_user_id="user_b",
            status=ConnectionStatus.REVOKED,
            permission=ConnectionPermission.FULL,
        )
        service._get_repo = MagicMock()
        repo_mock = MagicMock()
        repo_mock.get.return_value = conn
        service._get_repo.return_value = repo_mock

        with pytest.raises(ValueError, match="not active"):
            service.create_task_for_peer(
                user_id="user_a",
                connection_id="conn_test",
                title="Review my PR",
                assignee="orchestrator",
            )
```

- [ ] **Step 2: Implement cross-user task creation in ConnectionService**

Modify `src/gclaw/connection/service.py` -- update `__init__` to accept an optional `board_repo_factory` and add the `create_task_for_peer` method:

Update `__init__`:

```python
def __init__(
    self,
    db: FirestoreClient,
    board_repo_factory: object | None = None,
) -> None:
    self._db = db
    self._board_repo_factory = board_repo_factory
```

Add `create_task_for_peer` method:

```python
def create_task_for_peer(
    self,
    user_id: str,
    connection_id: str,
    title: str,
    assignee: str,
    description: str = "",
) -> BoardTask:
    """Create a task on a connected peer's board.

    Requires 'task' or 'full' permission on the connection.

    Args:
        user_id: The requesting user (task creator).
        connection_id: The connection to the target user.
        title: Task title.
        assignee: Agent to assign the task to on the peer's board.
        description: Task description.

    Returns:
        The created BoardTask on the peer's board.

    Raises:
        ValueError: If connection not found or not active.
        PermissionError: If insufficient permission.
        RuntimeError: If board_repo_factory not configured.
    """
    from gclaw.models.task import (
        BoardTask,
        TaskPriority,
        TaskSource,
        TaskSourceType,
        TaskStatus,
    )

    conn = self.check_permission(
        user_id=user_id,
        connection_id=connection_id,
        required=ConnectionPermission.TASK,
    )

    if self._board_repo_factory is None:
        raise RuntimeError("board_repo_factory not configured")

    # Determine the peer user
    peer_id = (
        conn.to_user_id
        if conn.from_user_id == user_id
        else conn.from_user_id
    )

    task = BoardTask(
        title=title,
        description=description,
        status=TaskStatus.QUEUED,
        priority=TaskPriority.MEDIUM,
        source=TaskSource(
            type=TaskSourceType.USER,
            origin=user_id,
        ),
        assignee=assignee,
    )

    peer_repo = self._board_repo_factory(peer_id)
    return peer_repo.create(task)
```

Also add the A2A task endpoint to `src/gclaw/api/connection_routes.py`:

```python
class CrossUserTaskRequest(BaseModel):
    connection_id: str
    title: str
    assignee: str
    description: str = ""
```

Add to the router:

```python
@router.post("/task")
def create_cross_user_task(
    body: CrossUserTaskRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Create a task on a connected user's board."""
    try:
        task = connection_service.create_task_for_peer(
            user_id=user_id,
            connection_id=body.connection_id,
            title=body.title,
            assignee=body.assignee,
            description=body.description,
        )
        return task.model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
```

- [ ] **Step 3: Run tests, verify all pass**

```bash
cd /mnt/c/Dev/GClaw && python -m pytest tests/test_cross_user_task.py -v
```

---

### Task 5: Onboarding Service (Interview Flow + Soul Generation)

**Files:**
- Create: `src/gclaw/models/onboarding.py`
- Create: `src/gclaw/onboarding/__init__.py`
- Create: `src/gclaw/onboarding/service.py`
- Create: `tests/test_onboarding_service.py`

- [ ] **Step 1: Write failing tests for the onboarding service**

Create `tests/test_onboarding_service.py`:

```python
"""Tests for the OnboardingService."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from gclaw.models.onboarding import OnboardingState, OnboardingStep
from gclaw.onboarding.service import OnboardingService


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def mock_agent_runner():
    runner = AsyncMock()
    runner.run.return_value = MagicMock(
        text="Tell me about your communication preferences."
    )
    return runner


@pytest.fixture
def mock_memory_service():
    return AsyncMock()


@pytest.fixture
def service(mock_db, mock_agent_runner, mock_memory_service):
    return OnboardingService(
        db=mock_db,
        agent_runner=mock_agent_runner,
        memory_service=mock_memory_service,
    )


class TestOnboardingState:
    def test_initial_state(self):
        state = OnboardingState(user_id="test_user")
        assert state.current_step == OnboardingStep.INTRODUCTION
        assert state.completed is False
        assert state.responses == {}

    def test_step_progression(self):
        """Steps follow the defined interview sequence."""
        steps = list(OnboardingStep)
        assert steps[0] == OnboardingStep.INTRODUCTION
        assert steps[-1] == OnboardingStep.COMPLETE


class TestStartOnboarding:
    @pytest.mark.asyncio
    async def test_creates_initial_state(self, service, mock_db):
        """Should create an onboarding state record and return intro message."""
        result = await service.start_onboarding("test_user")
        assert result["step"] == "introduction"
        assert "message" in result

    @pytest.mark.asyncio
    async def test_idempotent_if_already_started(self, service, mock_db):
        """Should return current state if onboarding already in progress."""
        # Mock existing state
        service._get_state = AsyncMock(
            return_value=OnboardingState(
                user_id="test_user",
                current_step=OnboardingStep.COMMUNICATION_STYLE,
            )
        )
        result = await service.start_onboarding("test_user")
        assert result["step"] == "communication_style"


class TestAdvanceOnboarding:
    @pytest.mark.asyncio
    async def test_stores_response_and_advances(
        self, service, mock_agent_runner
    ):
        """Should store user response and advance to next step."""
        service._get_state = AsyncMock(
            return_value=OnboardingState(
                user_id="test_user",
                current_step=OnboardingStep.COMMUNICATION_STYLE,
            )
        )
        service._save_state = AsyncMock()

        result = await service.advance_onboarding(
            user_id="test_user",
            response="I prefer casual but concise communication.",
        )
        assert result["step"] != "communication_style"
        mock_agent_runner.run.assert_called()

    @pytest.mark.asyncio
    async def test_advance_past_final_step_triggers_soul_gen(
        self, service, mock_agent_runner, mock_memory_service
    ):
        """Advancing past the last interview step triggers soul generation."""
        service._get_state = AsyncMock(
            return_value=OnboardingState(
                user_id="test_user",
                current_step=OnboardingStep.INITIAL_CRONS,
                responses={
                    "introduction": "Hi!",
                    "communication_style": "Casual and concise",
                    "daily_routines": "Morning person, gym at 6am",
                    "professional_context": "Software engineer",
                    "personal_context": "Likes hiking",
                },
            )
        )
        service._save_state = AsyncMock()
        service._generate_soul = AsyncMock(return_value="# Soul\nCasual tone")

        result = await service.advance_onboarding(
            user_id="test_user",
            response="Set up a morning briefing at 8am.",
        )
        assert result["step"] == "complete"
        assert result["completed"] is True
        service._generate_soul.assert_called_once()


class TestGenerateSoul:
    @pytest.mark.asyncio
    async def test_sends_responses_through_orchestrator(
        self, service, mock_agent_runner
    ):
        """Soul generation sends all responses to the orchestrator."""
        mock_agent_runner.run.return_value = MagicMock(
            text="# Soul Profile\n\n- Casual communication\n- Morning person"
        )
        responses = {
            "communication_style": "Casual",
            "daily_routines": "Morning person",
            "professional_context": "Engineer",
            "personal_context": "Hiker",
        }
        soul = await service._generate_soul("test_user", responses)
        assert "Soul" in soul
        mock_agent_runner.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_captures_soul_to_memory_bank(
        self, service, mock_agent_runner, mock_memory_service
    ):
        """Generated soul should be captured to Memory Bank."""
        mock_agent_runner.run.return_value = MagicMock(
            text="# Soul\nContent"
        )
        responses = {"communication_style": "Casual"}
        await service._generate_soul("test_user", responses)
        mock_memory_service.capture.assert_called()
```

- [ ] **Step 2: Implement the onboarding models**

Create `src/gclaw/models/onboarding.py`:

```python
"""Onboarding models for the conversational interview flow."""

from __future__ import annotations

from enum import Enum
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class OnboardingStep(str, Enum):
    """Interview steps in sequence."""

    INTRODUCTION = "introduction"
    COMMUNICATION_STYLE = "communication_style"
    DAILY_ROUTINES = "daily_routines"
    PROFESSIONAL_CONTEXT = "professional_context"
    PERSONAL_CONTEXT = "personal_context"
    INITIAL_CRONS = "initial_crons"
    COMPLETE = "complete"


# Ordered step sequence for progression
STEP_SEQUENCE: list[OnboardingStep] = list(OnboardingStep)


def next_step(current: OnboardingStep) -> OnboardingStep:
    """Return the next step in the sequence, or COMPLETE if at the end."""
    idx = STEP_SEQUENCE.index(current)
    if idx + 1 < len(STEP_SEQUENCE):
        return STEP_SEQUENCE[idx + 1]
    return OnboardingStep.COMPLETE


class OnboardingState(BaseModel):
    """Persistent onboarding state for a user.

    Stored at users/{userId}/profile.onboarding in Firestore.
    """

    user_id: str
    current_step: OnboardingStep = OnboardingStep.INTRODUCTION
    responses: dict[str, str] = Field(default_factory=dict)
    soul_content: str = ""
    completed: bool = False
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_firestore_dict(self) -> dict:
        return self.model_dump(mode="json")

    @classmethod
    def from_firestore_dict(cls, data: dict) -> OnboardingState:
        return cls(**data)
```

- [ ] **Step 3: Implement the OnboardingService**

Create `src/gclaw/onboarding/__init__.py` (empty).

Create `src/gclaw/onboarding/service.py`:

```python
"""Onboarding service — conversational interview and soul generation.

The onboarding flow is driven by the orchestrator agent. This service
tracks state, stores responses, and triggers soul file generation by
sending the collected interview through the orchestrator.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from gclaw.models.onboarding import (
    OnboardingState,
    OnboardingStep,
    next_step,
)

if TYPE_CHECKING:
    from google.cloud.firestore import Client as FirestoreClient

    from gclaw.dispatch.runner import AgentRunner
    from gclaw.memory.service import MemoryService

logger = logging.getLogger(__name__)

# System prompts for each interview step
_STEP_PROMPTS: dict[OnboardingStep, str] = {
    OnboardingStep.INTRODUCTION: (
        "You are onboarding a new user. Introduce yourself as GClaw, "
        "their personal AI assistant. Explain your capabilities briefly "
        "(task management, scheduling, research, smart home, etc.) and "
        "ask if they're ready to get started with a quick interview to "
        "personalize the experience."
    ),
    OnboardingStep.COMMUNICATION_STYLE: (
        "Ask the user about their communication preferences: "
        "Do they prefer casual or formal tone? Concise or detailed responses? "
        "Any specific style preferences (e.g., use of emoji, humor, etc.)?"
    ),
    OnboardingStep.DAILY_ROUTINES: (
        "Ask about the user's daily routines and priorities: "
        "What does a typical day look like? When do they wake up? "
        "What are their most important daily tasks or habits?"
    ),
    OnboardingStep.PROFESSIONAL_CONTEXT: (
        "Ask about the user's professional context: "
        "What is their role? What tools do they use daily? "
        "What workflows could benefit from automation?"
    ),
    OnboardingStep.PERSONAL_CONTEXT: (
        "Ask about personal context: interests, family, smart home setup, "
        "hobbies. Only what they're comfortable sharing — this helps "
        "personalize reminders and suggestions."
    ),
    OnboardingStep.INITIAL_CRONS: (
        "Based on what you've learned, suggest 2-3 initial automated routines "
        "(crons) that would be useful. Examples: morning briefing, inbox triage, "
        "end-of-day summary. Ask the user which ones they'd like to set up."
    ),
}

_SOUL_GENERATION_PROMPT = """\
Based on the following onboarding interview responses, generate a soul \
profile for this user. The soul profile should be a markdown document \
that captures:

- Communication style preferences
- Daily routines and priorities
- Professional context and workflows
- Personal interests and context
- General personality traits and preferences

Format it as a clean markdown document suitable for use as a base soul \
file (soul/base.md). Be specific and actionable — this will be injected \
into agent system prompts.

Interview responses:
{responses}
"""


class OnboardingService:
    """Manages the conversational onboarding interview flow.

    The orchestrator agent conducts the interview. This service
    tracks progress, stores responses, and triggers soul generation.
    """

    def __init__(
        self,
        db: FirestoreClient,
        agent_runner: AgentRunner,
        memory_service: MemoryService | None = None,
    ) -> None:
        self._db = db
        self._agent_runner = agent_runner
        self._memory_service = memory_service

    def _profile_ref(self, user_id: str):
        return (
            self._db.collection("users")
            .document(user_id)
        )

    async def _get_state(self, user_id: str) -> OnboardingState | None:
        """Load onboarding state from Firestore."""
        doc = self._profile_ref(user_id).get()
        if not doc.exists:
            return None
        data = doc.to_dict()
        onboarding_data = data.get("onboarding")
        if onboarding_data is None:
            return None
        return OnboardingState.from_firestore_dict(onboarding_data)

    async def _save_state(self, state: OnboardingState) -> None:
        """Persist onboarding state to Firestore."""
        self._profile_ref(state.user_id).set(
            {"onboarding": state.to_firestore_dict()},
            merge=True,
        )

    async def start_onboarding(self, user_id: str) -> dict:
        """Start or resume the onboarding interview.

        Returns:
            Dict with 'step' and 'message' keys.
        """
        existing = await self._get_state(user_id)
        if existing is not None and not existing.completed:
            # Resume from current step
            step = existing.current_step
            prompt = _STEP_PROMPTS.get(step, "")
            result = await self._agent_runner.run(
                user_id=user_id,
                message=prompt,
                session_id=f"onboarding_{user_id}",
            )
            return {
                "step": step.value,
                "message": result.text,
                "completed": False,
            }

        if existing is not None and existing.completed:
            return {
                "step": "complete",
                "message": "Onboarding already completed.",
                "completed": True,
            }

        # Create new onboarding state
        state = OnboardingState(user_id=user_id)
        await self._save_state(state)

        # Get introduction from orchestrator
        prompt = _STEP_PROMPTS[OnboardingStep.INTRODUCTION]
        result = await self._agent_runner.run(
            user_id=user_id,
            message=prompt,
            session_id=f"onboarding_{user_id}",
        )
        return {
            "step": "introduction",
            "message": result.text,
            "completed": False,
        }

    async def advance_onboarding(
        self,
        user_id: str,
        response: str,
    ) -> dict:
        """Process user response and advance to the next interview step.

        The user's response is stored, then the orchestrator is invoked
        with the next step's prompt to generate the next question.

        Args:
            user_id: The user being onboarded.
            response: The user's response to the current step.

        Returns:
            Dict with 'step', 'message', and 'completed' keys.
        """
        state = await self._get_state(user_id)
        if state is None:
            return await self.start_onboarding(user_id)

        if state.completed:
            return {
                "step": "complete",
                "message": "Onboarding already completed.",
                "completed": True,
            }

        # Store the response for the current step
        state.responses[state.current_step.value] = response

        # Advance to next step
        new_step = next_step(state.current_step)
        state.current_step = new_step
        state.updated_at = datetime.now(timezone.utc)

        if new_step == OnboardingStep.COMPLETE:
            # Generate soul from all responses
            soul_content = await self._generate_soul(
                user_id, state.responses
            )
            state.soul_content = soul_content
            state.completed = True
            await self._save_state(state)
            return {
                "step": "complete",
                "message": (
                    "Onboarding complete! Your soul profile has been "
                    "generated and saved."
                ),
                "completed": True,
                "soul_preview": soul_content[:500],
            }

        await self._save_state(state)

        # Get next question from orchestrator
        prompt = _STEP_PROMPTS.get(new_step, "")
        context = f"User's previous response: {response}\n\n{prompt}"
        result = await self._agent_runner.run(
            user_id=user_id,
            message=context,
            session_id=f"onboarding_{user_id}",
        )
        return {
            "step": new_step.value,
            "message": result.text,
            "completed": False,
        }

    async def _generate_soul(
        self,
        user_id: str,
        responses: dict[str, str],
    ) -> str:
        """Generate soul file content from interview responses.

        Sends all collected responses through the orchestrator to
        produce the soul profile markdown.
        """
        formatted_responses = "\n\n".join(
            f"**{step}:** {answer}"
            for step, answer in responses.items()
        )
        prompt = _SOUL_GENERATION_PROMPT.format(
            responses=formatted_responses
        )

        result = await self._agent_runner.run(
            user_id=user_id,
            message=prompt,
            session_id=f"onboarding_{user_id}_soul",
        )
        soul_content = result.text

        # Capture soul content to Memory Bank
        if self._memory_service is not None:
            try:
                await self._memory_service.capture(
                    user_id=user_id,
                    conversation_text=(
                        f"Onboarding interview completed. "
                        f"Soul profile generated:\n\n{soul_content}"
                    ),
                    topics=["USER_PREFERENCES", "EXPLICIT_INSTRUCTIONS"],
                )
            except Exception:
                logger.warning(
                    "Failed to capture soul to memory bank for %s",
                    user_id,
                    exc_info=True,
                )

        return soul_content

    async def get_status(self, user_id: str) -> dict:
        """Get onboarding completion status.

        Returns:
            Dict with 'completed', 'current_step', and 'progress' keys.
        """
        state = await self._get_state(user_id)
        if state is None:
            return {
                "completed": False,
                "current_step": None,
                "progress": 0.0,
            }

        total_steps = len(OnboardingStep) - 1  # exclude COMPLETE
        if state.completed:
            return {
                "completed": True,
                "current_step": "complete",
                "progress": 1.0,
            }

        current_idx = list(OnboardingStep).index(state.current_step)
        return {
            "completed": False,
            "current_step": state.current_step.value,
            "progress": current_idx / total_steps,
        }
```

- [ ] **Step 4: Run tests, verify all pass**

```bash
cd /mnt/c/Dev/GClaw && python -m pytest tests/test_onboarding_service.py -v
```

---

### Task 6: Onboarding API Endpoints

**Files:**
- Create: `src/gclaw/api/onboarding_routes.py`
- Modify: `src/gclaw/api/app.py`
- Create: `tests/test_onboarding_routes.py`

- [ ] **Step 1: Write failing tests for the onboarding endpoints**

Create `tests/test_onboarding_routes.py`:

```python
"""Tests for onboarding API routes."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gclaw.api.onboarding_routes import init_onboarding_router


@pytest.fixture
def mock_onboarding_service():
    return AsyncMock()


@pytest.fixture
def app(mock_onboarding_service):
    app = FastAPI()
    app.include_router(init_onboarding_router(mock_onboarding_service))
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture(autouse=True)
def mock_auth():
    with patch(
        "gclaw.api.onboarding_routes.get_current_user_id",
        return_value="test_user",
    ):
        yield


class TestStartOnboarding:
    def test_start_returns_intro(self, client, mock_onboarding_service):
        mock_onboarding_service.start_onboarding.return_value = {
            "step": "introduction",
            "message": "Welcome to GClaw!",
            "completed": False,
        }
        resp = client.post("/onboarding/start")
        assert resp.status_code == 200
        assert resp.json()["step"] == "introduction"


class TestAdvanceOnboarding:
    def test_advance_with_response(self, client, mock_onboarding_service):
        mock_onboarding_service.advance_onboarding.return_value = {
            "step": "daily_routines",
            "message": "Tell me about your daily routine.",
            "completed": False,
        }
        resp = client.post("/onboarding/advance", json={
            "response": "I prefer casual communication.",
        })
        assert resp.status_code == 200
        assert resp.json()["step"] == "daily_routines"


class TestOnboardingStatus:
    def test_status_returns_progress(self, client, mock_onboarding_service):
        mock_onboarding_service.get_status.return_value = {
            "completed": False,
            "current_step": "communication_style",
            "progress": 0.33,
        }
        resp = client.get("/onboarding/status")
        assert resp.status_code == 200
        assert resp.json()["progress"] == 0.33
```

- [ ] **Step 2: Implement the onboarding routes**

Create `src/gclaw/api/onboarding_routes.py`:

```python
"""API routes for the onboarding interview flow."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from gclaw.auth.dependencies import get_current_user_id
from gclaw.onboarding.service import OnboardingService


class AdvanceRequest(BaseModel):
    response: str


def init_onboarding_router(
    onboarding_service: OnboardingService,
) -> APIRouter:
    router = APIRouter(prefix="/onboarding", tags=["onboarding"])

    @router.post("/start")
    async def start_onboarding(
        user_id: str = Depends(get_current_user_id),
    ):
        return await onboarding_service.start_onboarding(user_id)

    @router.post("/advance")
    async def advance_onboarding(
        body: AdvanceRequest,
        user_id: str = Depends(get_current_user_id),
    ):
        return await onboarding_service.advance_onboarding(
            user_id=user_id,
            response=body.response,
        )

    @router.get("/status")
    async def onboarding_status(
        user_id: str = Depends(get_current_user_id),
    ):
        return await onboarding_service.get_status(user_id)

    return router
```

- [ ] **Step 3: Register the onboarding router in the app factory**

Modify `src/gclaw/api/app.py` -- add the import and router registration:

Add import at the top:

```python
from gclaw.api.onboarding_routes import init_onboarding_router
from gclaw.onboarding.service import OnboardingService
```

Add `onboarding_service: OnboardingService | None = None` parameter to `create_app`.

Add after the connection router registration block:

```python
if onboarding_service is not None:
    app.include_router(init_onboarding_router(onboarding_service))

# Store on app state
app.state.onboarding_service = onboarding_service
```

- [ ] **Step 4: Run tests, verify all pass**

```bash
cd /mnt/c/Dev/GClaw && python -m pytest tests/test_onboarding_routes.py -v
```

---

### Task 7: Frontend — Connections View + Onboarding Wizard

**Files:**
- Modify: `web/src/types/index.ts`
- Modify: `web/src/lib/api-client.ts`
- Create: `web/src/app/connections/page.tsx`
- Create: `web/src/components/connections/connection-list.tsx`
- Create: `web/src/components/connections/connection-request-form.tsx`
- Create: `web/src/components/connections/incoming-requests.tsx`
- Create: `web/src/components/connections/permission-editor.tsx`
- Create: `web/src/app/onboarding/page.tsx`
- Create: `web/src/components/onboarding/onboarding-wizard.tsx`
- Create: `web/src/components/onboarding/onboarding-chat.tsx`
- Create: `web/__tests__/connections-view.test.tsx`
- Create: `web/__tests__/onboarding-wizard.test.tsx`

- [ ] **Step 1: Add TypeScript types for connections and onboarding**

Modify `web/src/types/index.ts` -- add at the end of the file:

```typescript
/** Connection permission level. */
export type ConnectionPermission = "read" | "write" | "task" | "full";

/** Connection status. */
export type ConnectionStatus = "pending" | "active" | "rejected" | "revoked";

/** Cross-user connection record. */
export interface ConnectionInfo {
  id: string;
  from_user_id: string;
  to_user_id: string;
  status: ConnectionStatus;
  permission: ConnectionPermission;
  shared_channel: string;
  created_at: string;
  updated_at: string;
}

/** Request body for creating a connection. */
export interface ConnectionRequest {
  to_user_id: string;
  permission: ConnectionPermission;
}

/** Request body for creating a cross-user task. */
export interface CrossUserTaskRequest {
  connection_id: string;
  title: string;
  assignee: string;
  description?: string;
}

/** Onboarding step response from the API. */
export interface OnboardingStepResponse {
  step: string;
  message: string;
  completed: boolean;
  soul_preview?: string;
}

/** Onboarding status from the API. */
export interface OnboardingStatus {
  completed: boolean;
  current_step: string | null;
  progress: number;
}
```

- [ ] **Step 2: Add API client methods for connections and onboarding**

Modify `web/src/lib/api-client.ts` -- add the following methods to the `ApiClient` class:

```typescript
// --- Connections ---

async listConnections(): Promise<ConnectionInfo[]> {
  return this.get<ConnectionInfo[]>("/connections");
}

async listIncomingRequests(): Promise<ConnectionInfo[]> {
  return this.get<ConnectionInfo[]>("/connections/incoming");
}

async requestConnection(body: ConnectionRequest): Promise<ConnectionInfo> {
  return this.post<ConnectionInfo>("/connections/request", body);
}

async acceptConnection(connectionId: string): Promise<ConnectionInfo> {
  return this.post<ConnectionInfo>(`/connections/${connectionId}/accept`);
}

async rejectConnection(connectionId: string): Promise<ConnectionInfo> {
  return this.post<ConnectionInfo>(`/connections/${connectionId}/reject`);
}

async revokeConnection(connectionId: string): Promise<ConnectionInfo> {
  return this.post<ConnectionInfo>(`/connections/${connectionId}/revoke`);
}

async updateConnectionPermission(
  connectionId: string,
  permission: ConnectionPermission,
): Promise<ConnectionInfo> {
  return this.post<ConnectionInfo>(
    `/connections/${connectionId}/permission`,
    { permission },
  );
}

async createCrossUserTask(body: CrossUserTaskRequest): Promise<BoardTask> {
  return this.post<BoardTask>("/connections/task", body);
}

// --- Onboarding ---

async startOnboarding(): Promise<OnboardingStepResponse> {
  return this.post<OnboardingStepResponse>("/onboarding/start");
}

async advanceOnboarding(response: string): Promise<OnboardingStepResponse> {
  return this.post<OnboardingStepResponse>("/onboarding/advance", {
    response,
  });
}

async getOnboardingStatus(): Promise<OnboardingStatus> {
  return this.get<OnboardingStatus>("/onboarding/status");
}
```

- [ ] **Step 3: Create the Connections page and components**

Create `web/src/app/connections/page.tsx`:

```tsx
"use client";

import { useState } from "react";
import { ConnectionList } from "@/components/connections/connection-list";
import { ConnectionRequestForm } from "@/components/connections/connection-request-form";
import { IncomingRequests } from "@/components/connections/incoming-requests";

export default function ConnectionsPage() {
  const [refreshKey, setRefreshKey] = useState(0);
  const refresh = () => setRefreshKey((k) => k + 1);

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-8">
      <h1 className="text-2xl font-bold">Connections</h1>

      <section>
        <h2 className="text-lg font-semibold mb-4">Connect with a User</h2>
        <ConnectionRequestForm onSent={refresh} />
      </section>

      <section>
        <h2 className="text-lg font-semibold mb-4">Incoming Requests</h2>
        <IncomingRequests key={`incoming-${refreshKey}`} onAction={refresh} />
      </section>

      <section>
        <h2 className="text-lg font-semibold mb-4">Active Connections</h2>
        <ConnectionList key={`active-${refreshKey}`} onRevoke={refresh} />
      </section>
    </div>
  );
}
```

Create `web/src/components/connections/connection-list.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useApiClient } from "@/lib/api-client";
import { ConnectionInfo, ConnectionPermission } from "@/types";
import { PermissionEditor } from "./permission-editor";

interface ConnectionListProps {
  onRevoke?: () => void;
}

export function ConnectionList({ onRevoke }: ConnectionListProps) {
  const api = useApiClient();
  const [connections, setConnections] = useState<ConnectionInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .listConnections()
      .then(setConnections)
      .finally(() => setLoading(false));
  }, [api]);

  const handleRevoke = async (id: string) => {
    await api.revokeConnection(id);
    setConnections((prev) => prev.filter((c) => c.id !== id));
    onRevoke?.();
  };

  const handlePermissionChange = async (
    id: string,
    permission: ConnectionPermission,
  ) => {
    const updated = await api.updateConnectionPermission(id, permission);
    setConnections((prev) =>
      prev.map((c) => (c.id === id ? updated : c)),
    );
  };

  if (loading) return <p className="text-gray-500">Loading connections...</p>;
  if (connections.length === 0)
    return <p className="text-gray-500">No active connections.</p>;

  return (
    <div className="space-y-3">
      {connections.map((conn) => (
        <div
          key={conn.id}
          className="border rounded-lg p-4 flex items-center justify-between"
        >
          <div>
            <p className="font-medium">
              {conn.from_user_id === "me"
                ? conn.to_user_id
                : conn.from_user_id}
            </p>
            <p className="text-sm text-gray-500">
              Channel: {conn.shared_channel}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <PermissionEditor
              permission={conn.permission}
              onChange={(p) => handlePermissionChange(conn.id, p)}
            />
            <button
              onClick={() => handleRevoke(conn.id)}
              className="px-3 py-1 text-sm bg-red-100 text-red-700 rounded hover:bg-red-200"
            >
              Revoke
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
```

Create `web/src/components/connections/connection-request-form.tsx`:

```tsx
"use client";

import { useState } from "react";
import { useApiClient } from "@/lib/api-client";
import { ConnectionPermission } from "@/types";

interface ConnectionRequestFormProps {
  onSent?: () => void;
}

export function ConnectionRequestForm({ onSent }: ConnectionRequestFormProps) {
  const api = useApiClient();
  const [userId, setUserId] = useState("");
  const [permission, setPermission] = useState<ConnectionPermission>("read");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSuccess(false);
    try {
      await api.requestConnection({
        to_user_id: userId,
        permission,
      });
      setSuccess(true);
      setUserId("");
      onSent?.();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to send request");
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex gap-3 items-end">
      <div>
        <label className="block text-sm font-medium mb-1">User ID</label>
        <input
          type="text"
          value={userId}
          onChange={(e) => setUserId(e.target.value)}
          className="border rounded px-3 py-2"
          placeholder="Enter user ID"
          required
        />
      </div>
      <div>
        <label className="block text-sm font-medium mb-1">Permission</label>
        <select
          value={permission}
          onChange={(e) =>
            setPermission(e.target.value as ConnectionPermission)
          }
          className="border rounded px-3 py-2"
        >
          <option value="read">Read</option>
          <option value="write">Write</option>
          <option value="task">Task</option>
          <option value="full">Full</option>
        </select>
      </div>
      <button
        type="submit"
        className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
      >
        Send Request
      </button>
      {error && <p className="text-red-600 text-sm">{error}</p>}
      {success && (
        <p className="text-green-600 text-sm">Request sent!</p>
      )}
    </form>
  );
}
```

Create `web/src/components/connections/incoming-requests.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useApiClient } from "@/lib/api-client";
import { ConnectionInfo } from "@/types";

interface IncomingRequestsProps {
  onAction?: () => void;
}

export function IncomingRequests({ onAction }: IncomingRequestsProps) {
  const api = useApiClient();
  const [requests, setRequests] = useState<ConnectionInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .listIncomingRequests()
      .then(setRequests)
      .finally(() => setLoading(false));
  }, [api]);

  const handleAccept = async (id: string) => {
    await api.acceptConnection(id);
    setRequests((prev) => prev.filter((r) => r.id !== id));
    onAction?.();
  };

  const handleReject = async (id: string) => {
    await api.rejectConnection(id);
    setRequests((prev) => prev.filter((r) => r.id !== id));
    onAction?.();
  };

  if (loading) return <p className="text-gray-500">Loading...</p>;
  if (requests.length === 0)
    return <p className="text-gray-500">No incoming requests.</p>;

  return (
    <div className="space-y-3">
      {requests.map((req) => (
        <div
          key={req.id}
          className="border rounded-lg p-4 flex items-center justify-between"
        >
          <div>
            <p className="font-medium">{req.from_user_id}</p>
            <p className="text-sm text-gray-500">
              Requested permission: {req.permission}
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => handleAccept(req.id)}
              className="px-3 py-1 text-sm bg-green-100 text-green-700 rounded hover:bg-green-200"
            >
              Accept
            </button>
            <button
              onClick={() => handleReject(req.id)}
              className="px-3 py-1 text-sm bg-red-100 text-red-700 rounded hover:bg-red-200"
            >
              Reject
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
```

Create `web/src/components/connections/permission-editor.tsx`:

```tsx
"use client";

import { ConnectionPermission } from "@/types";

interface PermissionEditorProps {
  permission: ConnectionPermission;
  onChange: (permission: ConnectionPermission) => void;
}

export function PermissionEditor({
  permission,
  onChange,
}: PermissionEditorProps) {
  return (
    <select
      value={permission}
      onChange={(e) => onChange(e.target.value as ConnectionPermission)}
      className="border rounded px-2 py-1 text-sm"
    >
      <option value="read">Read</option>
      <option value="write">Write</option>
      <option value="task">Task</option>
      <option value="full">Full</option>
    </select>
  );
}
```

- [ ] **Step 4: Create the Onboarding wizard page and components**

Create `web/src/app/onboarding/page.tsx`:

```tsx
"use client";

import { OnboardingWizard } from "@/components/onboarding/onboarding-wizard";

export default function OnboardingPage() {
  return (
    <div className="max-w-2xl mx-auto p-6">
      <OnboardingWizard />
    </div>
  );
}
```

Create `web/src/components/onboarding/onboarding-wizard.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useApiClient } from "@/lib/api-client";
import { OnboardingStepResponse } from "@/types";
import { OnboardingChat } from "./onboarding-chat";

const STEP_LABELS: Record<string, string> = {
  introduction: "Welcome",
  communication_style: "Communication Style",
  daily_routines: "Daily Routines",
  professional_context: "Professional Context",
  personal_context: "Personal Context",
  initial_crons: "Initial Setup",
  complete: "Complete",
};

const STEP_ORDER = [
  "introduction",
  "communication_style",
  "daily_routines",
  "professional_context",
  "personal_context",
  "initial_crons",
  "complete",
];

export function OnboardingWizard() {
  const api = useApiClient();
  const [step, setStep] = useState<OnboardingStepResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .startOnboarding()
      .then(setStep)
      .finally(() => setLoading(false));
  }, [api]);

  const handleResponse = async (response: string) => {
    setLoading(true);
    try {
      const next = await api.advanceOnboarding(response);
      setStep(next);
    } finally {
      setLoading(false);
    }
  };

  if (loading && !step) {
    return <p className="text-gray-500">Starting onboarding...</p>;
  }

  if (step?.completed) {
    return (
      <div className="text-center space-y-4">
        <h2 className="text-2xl font-bold">You are all set!</h2>
        <p className="text-gray-600">
          Your soul profile has been generated. GClaw is ready to work for you.
        </p>
        {step.soul_preview && (
          <pre className="text-left bg-gray-100 rounded p-4 text-sm overflow-auto max-h-64">
            {step.soul_preview}
          </pre>
        )}
        <a
          href="/chat"
          className="inline-block px-6 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
        >
          Start Chatting
        </a>
      </div>
    );
  }

  const currentIdx = step
    ? STEP_ORDER.indexOf(step.step)
    : 0;
  const progress = ((currentIdx + 1) / STEP_ORDER.length) * 100;

  return (
    <div className="space-y-6">
      {/* Progress bar */}
      <div>
        <div className="flex justify-between text-sm text-gray-600 mb-1">
          <span>{STEP_LABELS[step?.step ?? "introduction"]}</span>
          <span>
            Step {currentIdx + 1} of {STEP_ORDER.length - 1}
          </span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2">
          <div
            className="bg-blue-600 h-2 rounded-full transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Chat-based interview */}
      {step && (
        <OnboardingChat
          agentMessage={step.message}
          onRespond={handleResponse}
          loading={loading}
        />
      )}
    </div>
  );
}
```

Create `web/src/components/onboarding/onboarding-chat.tsx`:

```tsx
"use client";

import { useState } from "react";

interface OnboardingChatProps {
  agentMessage: string;
  onRespond: (response: string) => void;
  loading: boolean;
}

export function OnboardingChat({
  agentMessage,
  onRespond,
  loading,
}: OnboardingChatProps) {
  const [input, setInput] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;
    onRespond(input.trim());
    setInput("");
  };

  return (
    <div className="space-y-4">
      {/* Agent message */}
      <div className="bg-gray-50 rounded-lg p-4">
        <p className="text-sm text-gray-500 mb-1">GClaw</p>
        <p className="whitespace-pre-wrap">{agentMessage}</p>
      </div>

      {/* User input */}
      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          className="flex-1 border rounded-lg px-4 py-2"
          placeholder="Type your response..."
          disabled={loading}
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "..." : "Send"}
        </button>
      </form>
    </div>
  );
}
```

- [ ] **Step 5: Add sidebar nav link for Connections page**

Modify the sidebar component (from Plan 4b) to add a "Connections" link after the existing nav items. Add the route:

```tsx
{ href: "/connections", label: "Connections", icon: UsersIcon },
```

- [ ] **Step 6: Write frontend tests**

Create `web/__tests__/connections-view.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect, beforeEach } from "vitest";
import ConnectionsPage from "@/app/connections/page";

const mockApi = {
  listConnections: vi.fn().mockResolvedValue([]),
  listIncomingRequests: vi.fn().mockResolvedValue([]),
  requestConnection: vi.fn().mockResolvedValue({ id: "c1" }),
  acceptConnection: vi.fn(),
  rejectConnection: vi.fn(),
  revokeConnection: vi.fn(),
  updateConnectionPermission: vi.fn(),
};

vi.mock("@/lib/api-client", () => ({
  useApiClient: () => mockApi,
}));

describe("ConnectionsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders all sections", async () => {
    render(<ConnectionsPage />);
    expect(screen.getByText("Connections")).toBeDefined();
    expect(screen.getByText("Connect with a User")).toBeDefined();
    expect(screen.getByText("Incoming Requests")).toBeDefined();
    expect(screen.getByText("Active Connections")).toBeDefined();
  });

  it("shows empty state for no connections", async () => {
    render(<ConnectionsPage />);
    await waitFor(() => {
      expect(screen.getByText("No active connections.")).toBeDefined();
    });
  });

  it("sends connection request on form submit", async () => {
    render(<ConnectionsPage />);
    const input = screen.getByPlaceholderText("Enter user ID");
    const button = screen.getByText("Send Request");

    await userEvent.type(input, "other_user");
    await userEvent.click(button);

    expect(mockApi.requestConnection).toHaveBeenCalledWith({
      to_user_id: "other_user",
      permission: "read",
    });
  });
});
```

Create `web/__tests__/onboarding-wizard.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect, beforeEach } from "vitest";
import OnboardingPage from "@/app/onboarding/page";

const mockApi = {
  startOnboarding: vi.fn().mockResolvedValue({
    step: "introduction",
    message: "Welcome to GClaw!",
    completed: false,
  }),
  advanceOnboarding: vi.fn().mockResolvedValue({
    step: "communication_style",
    message: "How do you like to communicate?",
    completed: false,
  }),
  getOnboardingStatus: vi.fn(),
};

vi.mock("@/lib/api-client", () => ({
  useApiClient: () => mockApi,
}));

describe("OnboardingPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders intro step on load", async () => {
    render(<OnboardingPage />);
    await waitFor(() => {
      expect(screen.getByText("Welcome to GClaw!")).toBeDefined();
    });
  });

  it("advances step on user response", async () => {
    render(<OnboardingPage />);
    await waitFor(() => {
      expect(screen.getByText("Welcome to GClaw!")).toBeDefined();
    });

    const input = screen.getByPlaceholderText("Type your response...");
    const button = screen.getByText("Send");
    await userEvent.type(input, "I prefer casual communication");
    await userEvent.click(button);

    expect(mockApi.advanceOnboarding).toHaveBeenCalledWith(
      "I prefer casual communication",
    );
  });

  it("shows completion state when done", async () => {
    mockApi.startOnboarding.mockResolvedValue({
      step: "complete",
      message: "Done!",
      completed: true,
      soul_preview: "# Soul\nCasual tone",
    });

    render(<OnboardingPage />);
    await waitFor(() => {
      expect(screen.getByText("You are all set!")).toBeDefined();
    });
    expect(screen.getByText("Start Chatting")).toBeDefined();
  });
});
```

- [ ] **Step 7: Run all frontend tests**

```bash
cd /mnt/c/Dev/GClaw/web && npx vitest run --reporter=verbose
```

---

### Task 8: Full Verification

**Files:** None (verification only)

- [ ] **Step 1: Run all backend tests**

```bash
cd /mnt/c/Dev/GClaw && python -m pytest tests/test_connection_model.py tests/test_connection_service.py tests/test_connection_routes.py tests/test_cross_user_task.py tests/test_onboarding_service.py tests/test_onboarding_routes.py -v
```

All tests must pass. If any fail, fix the issues and re-run.

- [ ] **Step 2: Run all frontend tests**

```bash
cd /mnt/c/Dev/GClaw/web && npx vitest run --reporter=verbose
```

All tests must pass. If any fail, fix the issues and re-run.

- [ ] **Step 3: Verify import chains and app factory wiring**

Start the app and verify the new routers are registered:

```bash
cd /mnt/c/Dev/GClaw && python -c "
from gclaw.models.connection import Connection, ConnectionPermission, ConnectionStatus
from gclaw.models.onboarding import OnboardingState, OnboardingStep
from gclaw.connection.service import ConnectionService
from gclaw.onboarding.service import OnboardingService
from gclaw.api.connection_routes import init_connection_router
from gclaw.api.onboarding_routes import init_onboarding_router
print('All imports OK')
"
```

- [ ] **Step 4: Verify Firestore schema alignment**

Confirm the following Firestore paths are used correctly:
- `users/{userId}/connections/{connectionId}` -- bilateral connection records
- `users/{userId}/profile.onboarding` -- onboarding state (nested in profile doc)
- `users/{userId}/board/{taskId}` -- cross-user tasks land on the target user's board

- [ ] **Step 5: Manual smoke test checklist**

Run the dev server and verify the following flows work end-to-end:

1. Navigate to `/connections` -- see empty state for all sections
2. Submit a connection request form -- request appears in sender's list
3. Navigate to `/onboarding` -- see introduction message from orchestrator
4. Type a response and submit -- see next interview question
5. Complete all steps -- see soul preview and "Start Chatting" link
6. Verify new nav sidebar link for "Connections" appears

- [ ] **Step 6: Confirm Python 3.10 compatibility**

Grep for any Python 3.11+ syntax (e.g., `match`/`case`, `ExceptionGroup`, `type X = ...`):

```bash
cd /mnt/c/Dev/GClaw && grep -rn "match " src/gclaw/connection/ src/gclaw/onboarding/ src/gclaw/models/connection.py src/gclaw/models/onboarding.py || echo "No match/case found"
```

Verify all `X | Y` union types use `from __future__ import annotations` at the top of each file.
