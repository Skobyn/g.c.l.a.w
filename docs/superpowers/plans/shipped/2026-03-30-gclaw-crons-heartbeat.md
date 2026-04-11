# GClaw Cron System & Heartbeat Consciousness Loop (Plan 2 of 4)

> **STATUS: shipped 2026-03-30 → 2026-03-31** — cron model/repo/service, cron routes, heartbeat context gatherer/service/route all landed in commits `d3d439e..6c0886d`. Archived 2026-04-11.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the cron scheduling system (Firestore-backed cron definitions with auto/todo modes) and the heartbeat consciousness loop (the orchestrator's proactive wake cycle that scans the board, gathers context, reasons about what needs attention, and takes action).

**Architecture:** Crons are Firestore documents that define scheduled tasks. Cloud Scheduler hits trigger endpoints to fire them. The heartbeat is a special cron that wakes the orchestrator to reason about the system state. Both systems build on Plan 1's BoardService, AgentFactory, and AgentRunner.

**Tech Stack:** Python 3.12, google-adk, FastAPI, google-cloud-firestore, Pydantic, pytest, Docker, Cloud Run

**Builds on Plan 1:**
- `BoardService` / `BoardRepo` for task creation and board scanning
- `AgentFactory` / `AgentRunner` for orchestrator reasoning
- `create_app` for adding new endpoints
- `Settings` for configuration

**Subsequent Plans:**
- Plan 3: Vertex AI Memory Bank + session compaction + skill system
- Plan 4: Next.js web app + voice + auth + multi-user A2A

---

## File Structure

```
gclaw/
├── src/
│   └── gclaw/
│       ├── models/
│       │   ├── task.py                    # (existing) Board task models
│       │   └── cron.py                    # NEW: Cron Pydantic model
│       ├── firestore/
│       │   ├── board_repo.py              # (existing)
│       │   └── cron_repo.py              # NEW: Cron Firestore CRUD
│       ├── cron/
│       │   ├── __init__.py
│       │   └── service.py                # NEW: Cron business logic
│       ├── heartbeat/
│       │   ├── __init__.py
│       │   ├── context.py                # NEW: Context gatherer for heartbeat
│       │   ├── service.py                # NEW: Heartbeat orchestration
│       │   └── log.py                    # NEW: Heartbeat logging model + repo
│       ├── api/
│       │   ├── app.py                    # MODIFY: add cron + heartbeat routers
│       │   ├── cron_routes.py            # NEW: Cron trigger endpoint
│       │   └── heartbeat_routes.py       # NEW: Heartbeat trigger endpoint
│       └── settings.py                   # MODIFY: add heartbeat config
├── tests/
│   ├── test_cron_model.py               # NEW
│   ├── test_cron_repo.py                # NEW
│   ├── test_cron_service.py             # NEW
│   ├── test_cron_routes.py              # NEW
│   ├── test_heartbeat_context.py        # NEW
│   ├── test_heartbeat_service.py        # NEW
│   ├── test_heartbeat_log.py            # NEW
│   └── test_heartbeat_routes.py         # NEW
└── crons/
    └── heartbeat.json                    # NEW: Default heartbeat config
```

---

### Task 1: Cron Model (Pydantic)

**Files:**
- Create: `src/gclaw/models/cron.py`
- Create: `tests/test_cron_model.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cron_model.py`:

```python
"""Tests for cron model."""

import pytest
from datetime import datetime, timezone

from gclaw.models.cron import (
    Cron,
    CronMode,
    CronStatus,
)


def test_create_minimal_cron():
    cron = Cron(
        title="Morning briefing",
        schedule="0 8 * * *",
        assignee="workspace-mgr",
    )
    assert cron.title == "Morning briefing"
    assert cron.schedule == "0 8 * * *"
    assert cron.assignee == "workspace-mgr"
    assert cron.mode == CronMode.TODO
    assert cron.status == CronStatus.ACTIVE
    assert cron.id.startswith("cron_")
    assert cron.created_at is not None


def test_create_auto_cron():
    cron = Cron(
        title="Inbox triage",
        schedule="*/30 * * * *",
        assignee="workspace-mgr",
        mode=CronMode.AUTO,
        description="Check and categorize new emails",
        task_priority="high",
    )
    assert cron.mode == CronMode.AUTO
    assert cron.description == "Check and categorize new emails"
    assert cron.task_priority == "high"


def test_create_paused_cron():
    cron = Cron(
        title="Weekly report",
        schedule="0 17 * * FRI",
        assignee="research-mgr",
        status=CronStatus.PAUSED,
    )
    assert cron.status == CronStatus.PAUSED


def test_cron_to_firestore_dict():
    cron = Cron(
        title="Test cron",
        schedule="0 9 * * *",
        assignee="dev-mgr",
    )
    d = cron.to_firestore_dict()
    assert d["title"] == "Test cron"
    assert d["schedule"] == "0 9 * * *"
    assert d["assignee"] == "dev-mgr"
    assert "id" not in d


def test_cron_from_firestore_dict():
    now = datetime.now(timezone.utc)
    d = {
        "title": "From Firestore",
        "description": "A cron from the DB",
        "schedule": "0 8 * * MON",
        "mode": "auto",
        "status": "active",
        "assignee": "workspace-mgr",
        "task_priority": "medium",
        "last_run": now,
        "next_run": now,
        "created_at": now,
        "updated_at": now,
    }
    cron = Cron.from_firestore_dict("cron_abc", d)
    assert cron.id == "cron_abc"
    assert cron.mode == CronMode.AUTO
    assert cron.status == CronStatus.ACTIVE
    assert cron.last_run == now


def test_cron_record_run():
    cron = Cron(
        title="Test",
        schedule="0 9 * * *",
        assignee="dev-mgr",
    )
    assert cron.last_run is None
    updated = cron.record_run()
    assert updated.last_run is not None
    assert updated.updated_at >= cron.updated_at
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cron_model.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gclaw.models.cron'`

- [ ] **Step 3: Implement cron model**

Create `src/gclaw/models/cron.py`:

```python
"""Cron model for scheduled task definitions."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field
from typing_extensions import Self


class CronMode(str, Enum):
    AUTO = "auto"
    TODO = "todo"


class CronStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"


class Cron(BaseModel):
    """A cron job definition stored in Firestore.

    When triggered:
    - mode="auto": creates a task on the board and immediately dispatches it
    - mode="todo": creates a task in backlog for manual prioritization
    """

    id: str = Field(default_factory=lambda: f"cron_{uuid.uuid4().hex[:12]}")
    title: str
    description: str = ""
    schedule: str  # cron expression, e.g. "0 8 * * *"
    mode: CronMode = CronMode.TODO
    status: CronStatus = CronStatus.ACTIVE
    assignee: str  # which agent handles the created task
    task_priority: str = "medium"  # priority for created tasks
    last_run: datetime | None = None
    next_run: datetime | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def record_run(self) -> Self:
        """Return a copy with last_run set to now."""
        now = datetime.now(timezone.utc)
        return self.model_copy(
            update={"last_run": now, "updated_at": now}
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

Run: `pytest tests/test_cron_model.py -v`
Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/gclaw/models/cron.py tests/test_cron_model.py
git commit -m "feat: cron Pydantic model with auto/todo modes and Firestore serialization"
```

---

### Task 2: Cron Firestore Repository

**Files:**
- Create: `src/gclaw/firestore/cron_repo.py`
- Create: `tests/test_cron_repo.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cron_repo.py`:

```python
"""Tests for cron repository.

Uses a mock Firestore client to test CRUD without a real database.
"""

import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone

from gclaw.models.cron import Cron, CronMode, CronStatus
from gclaw.firestore.cron_repo import CronRepo


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
    cron = Cron(
        title="Morning briefing",
        schedule="0 8 * * *",
        assignee="workspace-mgr",
    )
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
    cron = Cron(
        id="cron_abc",
        title="Updated cron",
        schedule="0 10 * * *",
        assignee="dev-mgr",
    )
    doc_ref = MagicMock()
    repo._db.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref

    repo.update(cron)

    doc_ref.set.assert_called_once()
    call_data = doc_ref.set.call_args[0][0]
    assert call_data["schedule"] == "0 10 * * *"


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cron_repo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gclaw.firestore.cron_repo'`

- [ ] **Step 3: Implement cron repository**

Create `src/gclaw/firestore/cron_repo.py`:

```python
"""Cron CRUD operations on Firestore.

Collection path: users/{userId}/crons/{cronId}
"""

from __future__ import annotations

from google.cloud.firestore import Client as FirestoreClient

from gclaw.models.cron import Cron, CronStatus


class CronRepo:
    """Synchronous Firestore repository for cron definitions."""

    def __init__(self, db: FirestoreClient, user_id: str) -> None:
        self._db = db
        self._user_id = user_id

    def _collection_ref(self):
        return (
            self._db.collection("users")
            .document(self._user_id)
            .collection("crons")
        )

    def create(self, cron: Cron) -> Cron:
        doc_ref = self._collection_ref().document(cron.id)
        doc_ref.set(cron.to_firestore_dict())
        return cron

    def get(self, cron_id: str) -> Cron | None:
        doc = self._collection_ref().document(cron_id).get()
        if not doc.exists:
            return None
        return Cron.from_firestore_dict(doc.id, doc.to_dict())

    def update(self, cron: Cron) -> Cron:
        doc_ref = self._collection_ref().document(cron.id)
        doc_ref.set(cron.to_firestore_dict())
        return cron

    def delete(self, cron_id: str) -> None:
        self._collection_ref().document(cron_id).delete()

    def list_all(self) -> list[Cron]:
        docs = self._collection_ref().stream()
        return [
            Cron.from_firestore_dict(doc.id, doc.to_dict()) for doc in docs
        ]

    def list_active(self) -> list[Cron]:
        docs = (
            self._collection_ref()
            .where("status", "==", CronStatus.ACTIVE.value)
            .stream()
        )
        return [
            Cron.from_firestore_dict(doc.id, doc.to_dict()) for doc in docs
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cron_repo.py -v`
Expected: All 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/gclaw/firestore/cron_repo.py tests/test_cron_repo.py
git commit -m "feat: Firestore cron repository with CRUD and active listing"
```

---

### Task 3: Cron Service (Business Logic)

**Files:**
- Create: `src/gclaw/cron/__init__.py`
- Create: `src/gclaw/cron/service.py`
- Create: `tests/test_cron_service.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cron_service.py`:

```python
"""Tests for cron service business logic."""

import pytest
from unittest.mock import MagicMock

from gclaw.models.cron import Cron, CronMode, CronStatus
from gclaw.models.task import BoardTask, TaskStatus, TaskSourceType
from gclaw.cron.service import CronService


@pytest.fixture
def cron_repo():
    return MagicMock()


@pytest.fixture
def board_service():
    return MagicMock()


@pytest.fixture
def service(cron_repo, board_service):
    return CronService(cron_repo=cron_repo, board_service=board_service)


def test_create_cron(service, cron_repo):
    cron_repo.create.side_effect = lambda c: c
    cron = service.create(
        title="Morning briefing",
        schedule="0 8 * * *",
        assignee="workspace-mgr",
        mode="todo",
        description="Daily morning update",
    )
    assert cron.title == "Morning briefing"
    assert cron.mode == CronMode.TODO
    assert cron.status == CronStatus.ACTIVE
    cron_repo.create.assert_called_once()


def test_update_cron(service, cron_repo):
    existing = Cron(
        id="cron_1",
        title="Old title",
        schedule="0 8 * * *",
        assignee="workspace-mgr",
    )
    cron_repo.get.return_value = existing
    cron_repo.update.side_effect = lambda c: c

    updated = service.update(
        cron_id="cron_1",
        title="New title",
        schedule="0 9 * * *",
    )
    assert updated.title == "New title"
    assert updated.schedule == "0 9 * * *"
    cron_repo.update.assert_called_once()


def test_update_nonexistent_raises(service, cron_repo):
    cron_repo.get.return_value = None
    with pytest.raises(ValueError, match="not found"):
        service.update(cron_id="cron_nope", title="X")


def test_delete_cron(service, cron_repo):
    service.delete("cron_1")
    cron_repo.delete.assert_called_once_with("cron_1")


def test_list_crons(service, cron_repo):
    cron_repo.list_all.return_value = [
        Cron(title="C1", schedule="0 8 * * *", assignee="dev-mgr"),
        Cron(title="C2", schedule="0 9 * * *", assignee="workspace-mgr"),
    ]
    crons = service.list_all()
    assert len(crons) == 2


def test_pause_cron(service, cron_repo):
    cron = Cron(
        id="cron_1",
        title="Active cron",
        schedule="0 8 * * *",
        assignee="workspace-mgr",
        status=CronStatus.ACTIVE,
    )
    cron_repo.get.return_value = cron
    cron_repo.update.side_effect = lambda c: c

    paused = service.pause("cron_1")
    assert paused.status == CronStatus.PAUSED


def test_resume_cron(service, cron_repo):
    cron = Cron(
        id="cron_1",
        title="Paused cron",
        schedule="0 8 * * *",
        assignee="workspace-mgr",
        status=CronStatus.PAUSED,
    )
    cron_repo.get.return_value = cron
    cron_repo.update.side_effect = lambda c: c

    resumed = service.resume("cron_1")
    assert resumed.status == CronStatus.ACTIVE


def test_execute_todo_mode(service, cron_repo, board_service):
    cron = Cron(
        id="cron_1",
        title="Todo cron",
        schedule="0 8 * * *",
        assignee="workspace-mgr",
        mode=CronMode.TODO,
        description="Check emails",
        task_priority="medium",
    )
    cron_repo.get.return_value = cron
    cron_repo.update.side_effect = lambda c: c
    board_service.create_task.side_effect = lambda **kw: BoardTask(
        title=kw["title"], assignee=kw["assignee"]
    )

    task = service.execute("cron_1")

    board_service.create_task.assert_called_once()
    call_kwargs = board_service.create_task.call_args.kwargs
    assert call_kwargs["title"] == "Todo cron"
    assert call_kwargs["status"] == TaskStatus.BACKLOG
    assert call_kwargs["source_type"] == "cron"
    assert call_kwargs["source_origin"] == "cron_1"


def test_execute_auto_mode(service, cron_repo, board_service):
    cron = Cron(
        id="cron_2",
        title="Auto cron",
        schedule="*/30 * * * *",
        assignee="workspace-mgr",
        mode=CronMode.AUTO,
        description="Triage inbox",
        task_priority="high",
    )
    cron_repo.get.return_value = cron
    cron_repo.update.side_effect = lambda c: c
    board_service.create_task.side_effect = lambda **kw: BoardTask(
        title=kw["title"], assignee=kw["assignee"], status=TaskStatus(kw.get("status", "backlog"))
    )

    task = service.execute("cron_2")

    call_kwargs = board_service.create_task.call_args.kwargs
    assert call_kwargs["status"] == TaskStatus.QUEUED
    assert call_kwargs["priority"] == "high"


def test_execute_paused_cron_raises(service, cron_repo):
    cron = Cron(
        id="cron_1",
        title="Paused",
        schedule="0 8 * * *",
        assignee="workspace-mgr",
        status=CronStatus.PAUSED,
    )
    cron_repo.get.return_value = cron

    with pytest.raises(ValueError, match="paused"):
        service.execute("cron_1")


def test_execute_nonexistent_raises(service, cron_repo):
    cron_repo.get.return_value = None
    with pytest.raises(ValueError, match="not found"):
        service.execute("cron_nope")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cron_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gclaw.cron'`

- [ ] **Step 3: Implement cron service**

Create `src/gclaw/cron/__init__.py`:

```python
"""Cron scheduling and execution."""
```

Create `src/gclaw/cron/service.py`:

```python
"""Cron service — business logic for scheduled task management."""

from __future__ import annotations

from gclaw.board.service import BoardService
from gclaw.firestore.cron_repo import CronRepo
from gclaw.models.cron import Cron, CronMode, CronStatus
from gclaw.models.task import TaskStatus


class CronService:
    """High-level operations on cron definitions."""

    def __init__(
        self,
        cron_repo: CronRepo,
        board_service: BoardService,
    ) -> None:
        self._repo = cron_repo
        self._board = board_service

    def create(
        self,
        title: str,
        schedule: str,
        assignee: str,
        mode: str = "todo",
        description: str = "",
        task_priority: str = "medium",
    ) -> Cron:
        cron = Cron(
            title=title,
            description=description,
            schedule=schedule,
            mode=CronMode(mode),
            assignee=assignee,
            task_priority=task_priority,
        )
        return self._repo.create(cron)

    def update(
        self,
        cron_id: str,
        title: str | None = None,
        schedule: str | None = None,
        mode: str | None = None,
        description: str | None = None,
        assignee: str | None = None,
        task_priority: str | None = None,
    ) -> Cron:
        cron = self._repo.get(cron_id)
        if cron is None:
            raise ValueError(f"Cron {cron_id} not found")

        updates: dict = {}
        if title is not None:
            updates["title"] = title
        if schedule is not None:
            updates["schedule"] = schedule
        if mode is not None:
            updates["mode"] = CronMode(mode)
        if description is not None:
            updates["description"] = description
        if assignee is not None:
            updates["assignee"] = assignee
        if task_priority is not None:
            updates["task_priority"] = task_priority

        updated = cron.model_copy(update=updates)
        return self._repo.update(updated)

    def delete(self, cron_id: str) -> None:
        self._repo.delete(cron_id)

    def list_all(self) -> list[Cron]:
        return self._repo.list_all()

    def pause(self, cron_id: str) -> Cron:
        cron = self._repo.get(cron_id)
        if cron is None:
            raise ValueError(f"Cron {cron_id} not found")
        paused = cron.model_copy(update={"status": CronStatus.PAUSED})
        return self._repo.update(paused)

    def resume(self, cron_id: str) -> Cron:
        cron = self._repo.get(cron_id)
        if cron is None:
            raise ValueError(f"Cron {cron_id} not found")
        resumed = cron.model_copy(update={"status": CronStatus.ACTIVE})
        return self._repo.update(resumed)

    def execute(self, cron_id: str) -> None:
        """Execute a cron: create a task on the board based on mode.

        - mode="todo": create task in BACKLOG
        - mode="auto": create task in QUEUED (ready for immediate pickup)

        Returns the created BoardTask.
        """
        cron = self._repo.get(cron_id)
        if cron is None:
            raise ValueError(f"Cron {cron_id} not found")
        if cron.status == CronStatus.PAUSED:
            raise ValueError(
                f"Cron {cron_id} is paused — resume it before executing"
            )

        # Determine task status based on cron mode
        if cron.mode == CronMode.AUTO:
            task_status = TaskStatus.QUEUED
        else:
            task_status = TaskStatus.BACKLOG

        # Create the task on the board
        task = self._board.create_task(
            title=cron.title,
            assignee=cron.assignee,
            description=cron.description,
            priority=cron.task_priority,
            source_type="cron",
            source_origin=cron.id,
            status=task_status,
        )

        # Record the run
        updated_cron = cron.record_run()
        self._repo.update(updated_cron)

        return task
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cron_service.py -v`
Expected: All 11 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/gclaw/cron/ tests/test_cron_service.py
git commit -m "feat: cron service with create, update, pause/resume, and execute"
```

---

### Task 4: Cron Trigger Endpoint

**Files:**
- Create: `src/gclaw/api/cron_routes.py`
- Create: `tests/test_cron_routes.py`
- Modify: `src/gclaw/api/app.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cron_routes.py`:

```python
"""Tests for cron API endpoints."""

import pytest
from unittest.mock import MagicMock
from httpx import AsyncClient, ASGITransport

from gclaw.api.app import create_app
from gclaw.models.cron import Cron, CronMode, CronStatus
from gclaw.models.task import BoardTask, TaskStatus


@pytest.fixture
def board_service():
    svc = MagicMock()
    svc.get_all_tasks.return_value = []
    return svc


@pytest.fixture
def agent_runner():
    from unittest.mock import AsyncMock
    return AsyncMock()


@pytest.fixture
def cron_service():
    return MagicMock()


@pytest.fixture
def heartbeat_service():
    return None


@pytest.fixture
def app(board_service, agent_runner, cron_service, heartbeat_service):
    return create_app(
        board_service=board_service,
        agent_runner=agent_runner,
        cron_service=cron_service,
        heartbeat_service=heartbeat_service,
    )


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_trigger_cron(client, cron_service):
    cron_service.execute.return_value = BoardTask(
        title="Morning briefing",
        assignee="workspace-mgr",
        status=TaskStatus.BACKLOG,
    )
    resp = await client.post("/crons/cron_abc/trigger")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "triggered"
    assert data["cron_id"] == "cron_abc"
    cron_service.execute.assert_called_once_with("cron_abc")


@pytest.mark.asyncio
async def test_trigger_nonexistent_cron(client, cron_service):
    cron_service.execute.side_effect = ValueError("Cron cron_nope not found")
    resp = await client.post("/crons/cron_nope/trigger")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_trigger_paused_cron(client, cron_service):
    cron_service.execute.side_effect = ValueError("Cron cron_1 is paused")
    resp = await client.post("/crons/cron_1/trigger")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_crons(client, cron_service):
    cron_service.list_all.return_value = [
        Cron(title="C1", schedule="0 8 * * *", assignee="dev-mgr"),
        Cron(title="C2", schedule="0 9 * * *", assignee="workspace-mgr"),
    ]
    resp = await client.get("/crons")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["title"] == "C1"


@pytest.mark.asyncio
async def test_create_cron(client, cron_service):
    cron_service.create.side_effect = lambda **kw: Cron(
        title=kw["title"],
        schedule=kw["schedule"],
        assignee=kw["assignee"],
    )
    resp = await client.post("/crons", json={
        "title": "New cron",
        "schedule": "0 8 * * *",
        "assignee": "workspace-mgr",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "New cron"
    cron_service.create.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cron_routes.py -v`
Expected: FAIL — `ImportError` or `TypeError` because `create_app` doesn't accept `cron_service` yet.

- [ ] **Step 3: Implement cron routes**

Create `src/gclaw/api/cron_routes.py`:

```python
"""Cron management and trigger endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from gclaw.cron.service import CronService

router = APIRouter(prefix="/crons")

_cron_service: CronService | None = None


def init_cron_router(cron_service: CronService) -> APIRouter:
    global _cron_service
    _cron_service = cron_service
    return router


class CreateCronRequest(BaseModel):
    title: str
    schedule: str
    assignee: str
    mode: str = "todo"
    description: str = ""
    task_priority: str = "medium"


@router.get("")
def list_crons():
    crons = _cron_service.list_all()
    return [c.model_dump(mode="json") for c in crons]


@router.post("", status_code=201)
def create_cron(req: CreateCronRequest):
    cron = _cron_service.create(
        title=req.title,
        schedule=req.schedule,
        assignee=req.assignee,
        mode=req.mode,
        description=req.description,
        task_priority=req.task_priority,
    )
    return cron.model_dump(mode="json")


@router.post("/{cron_id}/trigger")
def trigger_cron(cron_id: str):
    try:
        task = _cron_service.execute(cron_id)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg)
        if "paused" in msg:
            raise HTTPException(status_code=400, detail=msg)
        raise HTTPException(status_code=400, detail=msg)

    return {
        "status": "triggered",
        "cron_id": cron_id,
        "task_id": task.id,
        "task_status": task.status.value,
    }
```

- [ ] **Step 4: Update create_app to accept cron_service**

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
) -> FastAPI:
    app = FastAPI(title="GClaw", version="0.2.0")

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

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app
```

- [ ] **Step 5: Create placeholder heartbeat_routes to satisfy the import**

Create `src/gclaw/api/heartbeat_routes.py` (placeholder that will be fully implemented in Task 6):

```python
"""Heartbeat trigger endpoint — placeholder until Task 6."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


def init_heartbeat_router(heartbeat_service: object) -> APIRouter:
    return router
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_cron_routes.py -v`
Expected: All 5 tests PASS.

Run: `pytest tests/test_api.py -v`
Expected: All existing API tests still PASS (backward compatible — cron_service defaults to None).

- [ ] **Step 7: Commit**

```bash
git add src/gclaw/api/cron_routes.py src/gclaw/api/heartbeat_routes.py src/gclaw/api/app.py tests/test_cron_routes.py
git commit -m "feat: cron trigger and management endpoints with updated app factory"
```

---

### Task 5: Heartbeat Context Gatherer

**Files:**
- Create: `src/gclaw/heartbeat/__init__.py`
- Create: `src/gclaw/heartbeat/context.py`
- Create: `tests/test_heartbeat_context.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_heartbeat_context.py`:

```python
"""Tests for heartbeat context gatherer."""

import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone

from gclaw.models.task import BoardTask, TaskStatus, TaskPriority
from gclaw.models.cron import Cron, CronMode
from gclaw.heartbeat.context import HeartbeatContextGatherer


@pytest.fixture
def board_service():
    return MagicMock()


@pytest.fixture
def cron_service():
    return MagicMock()


@pytest.fixture
def gatherer(board_service, cron_service):
    return HeartbeatContextGatherer(
        board_service=board_service,
        cron_service=cron_service,
    )


def test_gather_empty_board(gatherer, board_service, cron_service):
    board_service.get_all_tasks.return_value = []
    cron_service.list_all.return_value = []

    ctx = gatherer.gather()

    assert "current_time" in ctx
    assert ctx["board_summary"]["total_tasks"] == 0
    assert ctx["board_summary"]["queued"] == 0
    assert ctx["board_summary"]["in_progress"] == 0
    assert ctx["board_summary"]["failed"] == 0
    assert ctx["board_summary"]["needs_approval"] == 0
    assert ctx["stale_tasks"] == []
    assert ctx["failed_tasks"] == []
    assert ctx["pending_approvals"] == []
    assert ctx["cron_summary"]["total_crons"] == 0


def test_gather_with_tasks(gatherer, board_service, cron_service):
    tasks = [
        BoardTask(
            id="t1", title="Queued task", assignee="dev-mgr",
            status=TaskStatus.QUEUED, priority=TaskPriority.HIGH,
        ),
        BoardTask(
            id="t2", title="In progress task", assignee="workspace-mgr",
            status=TaskStatus.IN_PROGRESS,
        ),
        BoardTask(
            id="t3", title="Failed task", assignee="dev-mgr",
            status=TaskStatus.FAILED,
        ),
        BoardTask(
            id="t4", title="Needs approval", assignee="comms-mgr",
            status=TaskStatus.NEEDS_APPROVAL,
        ),
        BoardTask(
            id="t5", title="Done task", assignee="dev-mgr",
            status=TaskStatus.DONE,
        ),
    ]
    board_service.get_all_tasks.return_value = tasks
    cron_service.list_all.return_value = []

    ctx = gatherer.gather()

    assert ctx["board_summary"]["total_tasks"] == 5
    assert ctx["board_summary"]["queued"] == 1
    assert ctx["board_summary"]["in_progress"] == 1
    assert ctx["board_summary"]["failed"] == 1
    assert ctx["board_summary"]["needs_approval"] == 1
    assert ctx["board_summary"]["done"] == 1
    assert len(ctx["failed_tasks"]) == 1
    assert ctx["failed_tasks"][0]["id"] == "t3"
    assert len(ctx["pending_approvals"]) == 1
    assert ctx["pending_approvals"][0]["id"] == "t4"


def test_gather_with_crons(gatherer, board_service, cron_service):
    board_service.get_all_tasks.return_value = []
    cron_service.list_all.return_value = [
        Cron(title="C1", schedule="0 8 * * *", assignee="dev-mgr"),
        Cron(title="C2", schedule="0 9 * * *", assignee="workspace-mgr",
             mode=CronMode.AUTO),
    ]

    ctx = gatherer.gather()

    assert ctx["cron_summary"]["total_crons"] == 2


def test_gather_formats_as_message(gatherer, board_service, cron_service):
    board_service.get_all_tasks.return_value = [
        BoardTask(
            id="t1", title="Failed task", assignee="dev-mgr",
            status=TaskStatus.FAILED,
        ),
    ]
    cron_service.list_all.return_value = []

    message = gatherer.gather_as_message()

    assert isinstance(message, str)
    assert "Heartbeat" in message
    assert "failed" in message.lower()
    assert "t1" in message
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_heartbeat_context.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gclaw.heartbeat'`

- [ ] **Step 3: Implement heartbeat context gatherer**

Create `src/gclaw/heartbeat/__init__.py`:

```python
"""Heartbeat consciousness loop — the orchestrator's proactive wake cycle."""
```

Create `src/gclaw/heartbeat/context.py`:

```python
"""Context gatherer for the heartbeat consciousness loop.

Scans the board, crons, and system state to build a context snapshot
that the orchestrator uses to decide what actions to take.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from gclaw.board.service import BoardService
from gclaw.cron.service import CronService
from gclaw.models.task import TaskStatus


class HeartbeatContextGatherer:
    """Gathers world state for the orchestrator's heartbeat reasoning."""

    def __init__(
        self,
        board_service: BoardService,
        cron_service: CronService,
    ) -> None:
        self._board = board_service
        self._crons = cron_service

    def gather(self) -> dict:
        """Gather full context snapshot for heartbeat reasoning.

        Returns a dict with:
        - current_time: ISO timestamp
        - board_summary: task counts by status
        - failed_tasks: list of failed task summaries
        - pending_approvals: tasks needing user approval
        - stale_tasks: tasks stuck in progress (placeholder for time-based check)
        - cron_summary: overview of cron definitions
        - memories: placeholder for Vertex AI Memory Bank (Plan 3)
        """
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
            # Placeholder for Plan 3
            "memories": [],
        }

    def gather_as_message(self) -> str:
        """Gather context and format it as a message for the orchestrator.

        This is what gets sent to the orchestrator agent as a user message
        during the heartbeat cycle, so it can reason about what to do.
        """
        ctx = self.gather()
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
                parts.append(f"- {m}")

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

Run: `pytest tests/test_heartbeat_context.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/gclaw/heartbeat/ tests/test_heartbeat_context.py
git commit -m "feat: heartbeat context gatherer scans board and crons for orchestrator reasoning"
```

---

### Task 6: Heartbeat Service & Logging

**Files:**
- Create: `src/gclaw/heartbeat/log.py`
- Create: `src/gclaw/heartbeat/service.py`
- Create: `tests/test_heartbeat_log.py`
- Create: `tests/test_heartbeat_service.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_heartbeat_log.py`:

```python
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
```

Create `tests/test_heartbeat_service.py`:

```python
"""Tests for heartbeat service — the consciousness loop."""

import pytest
from unittest.mock import MagicMock, AsyncMock

from gclaw.heartbeat.service import HeartbeatService
from gclaw.dispatch.runner import AgentResponse


@pytest.fixture
def context_gatherer():
    gatherer = MagicMock()
    gatherer.gather.return_value = {
        "current_time": "2026-03-30T12:00:00+00:00",
        "board_summary": {
            "total_tasks": 2,
            "backlog": 0,
            "queued": 1,
            "in_progress": 0,
            "needs_approval": 0,
            "done": 0,
            "failed": 1,
        },
        "failed_tasks": [
            {"id": "t3", "title": "Failed task", "assignee": "dev-mgr"}
        ],
        "pending_approvals": [],
        "stale_tasks": [],
        "cron_summary": {"total_crons": 2},
        "memories": [],
    }
    gatherer.gather_as_message.return_value = (
        "## Heartbeat Wake Cycle\n\n"
        "**Time:** 2026-03-30T12:00:00+00:00\n\n"
        "### Board Summary\n"
        "- Total tasks: 2\n"
        "- Failed: 1\n\n"
        "### Failed Tasks\n"
        "- [t3] Failed task (assignee: dev-mgr)\n"
    )
    return gatherer


@pytest.fixture
def agent_runner():
    runner = AsyncMock()
    runner.run.return_value = AgentResponse(
        text="I see a failed task t3. I'll create a retry task for it.",
        tool_calls=[
            {
                "name": "create_board_task",
                "args": {
                    "title": "Retry: Failed task",
                    "assignee": "dev-mgr",
                },
            }
        ],
        is_final=True,
    )
    return runner


@pytest.fixture
def log_repo():
    return MagicMock()


@pytest.fixture
def service(context_gatherer, agent_runner, log_repo):
    return HeartbeatService(
        context_gatherer=context_gatherer,
        agent_runner=agent_runner,
        log_repo=log_repo,
        user_id="user_123",
        session_id="heartbeat_session",
    )


@pytest.mark.asyncio
async def test_heartbeat_runs_full_cycle(service, context_gatherer, agent_runner, log_repo):
    result = await service.run()

    # Context was gathered
    context_gatherer.gather.assert_called_once()
    context_gatherer.gather_as_message.assert_called_once()

    # Orchestrator was invoked
    agent_runner.run.assert_called_once()
    call_kwargs = agent_runner.run.call_args.kwargs
    assert call_kwargs["user_id"] == "user_123"
    assert call_kwargs["session_id"] == "heartbeat_session"
    assert "Heartbeat" in call_kwargs["message"]

    # Log was saved
    log_repo.save.assert_called_once()

    # Result contains the orchestrator's response
    assert "failed task" in result["orchestrator_response"].lower()
    assert result["actions_taken"] is not None


@pytest.mark.asyncio
async def test_heartbeat_silent_when_board_empty(log_repo):
    gatherer = MagicMock()
    gatherer.gather.return_value = {
        "current_time": "2026-03-30T12:00:00+00:00",
        "board_summary": {
            "total_tasks": 0,
            "backlog": 0,
            "queued": 0,
            "in_progress": 0,
            "needs_approval": 0,
            "done": 0,
            "failed": 0,
        },
        "failed_tasks": [],
        "pending_approvals": [],
        "stale_tasks": [],
        "cron_summary": {"total_crons": 0},
        "memories": [],
    }
    gatherer.gather_as_message.return_value = (
        "## Heartbeat Wake Cycle\n\n"
        "Board is empty. Nothing to do."
    )

    runner = AsyncMock()
    runner.run.return_value = AgentResponse(
        text="All quiet. Going back to sleep.",
        tool_calls=[],
        is_final=True,
    )

    service = HeartbeatService(
        context_gatherer=gatherer,
        agent_runner=runner,
        log_repo=log_repo,
        user_id="user_123",
        session_id="heartbeat_session",
    )

    result = await service.run()

    assert "quiet" in result["orchestrator_response"].lower() or "sleep" in result["orchestrator_response"].lower()
    log_repo.save.assert_called_once()


@pytest.mark.asyncio
async def test_heartbeat_logs_context_summary(service, log_repo):
    await service.run()

    saved_log = log_repo.save.call_args[0][0]
    assert saved_log.context_summary is not None
    assert "2" in saved_log.context_summary or "tasks" in saved_log.context_summary.lower()
    assert saved_log.reasoning is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_heartbeat_log.py tests/test_heartbeat_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gclaw.heartbeat.log'` and `No module named 'gclaw.heartbeat.service'`

- [ ] **Step 3: Implement heartbeat log**

Create `src/gclaw/heartbeat/log.py`:

```python
"""Heartbeat logging model and Firestore repository.

Collection path: users/{userId}/heartbeat_logs/{logId}
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from typing_extensions import Self
from google.cloud.firestore import Client as FirestoreClient


class HeartbeatLog(BaseModel):
    """A single heartbeat cycle log entry."""

    id: str = Field(default_factory=lambda: f"hb_{uuid.uuid4().hex[:12]}")
    context_summary: str
    reasoning: str
    actions_taken: list[str] = Field(default_factory=list)
    tasks_created: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_firestore_dict(self) -> dict:
        d = self.model_dump(mode="json")
        d.pop("id")
        return d

    @classmethod
    def from_firestore_dict(cls, doc_id: str, data: dict) -> Self:
        return cls(id=doc_id, **data)


class HeartbeatLogRepo:
    """Firestore repository for heartbeat logs."""

    def __init__(self, db: FirestoreClient, user_id: str) -> None:
        self._db = db
        self._user_id = user_id

    def _collection_ref(self):
        return (
            self._db.collection("users")
            .document(self._user_id)
            .collection("heartbeat_logs")
        )

    def save(self, log: HeartbeatLog) -> HeartbeatLog:
        doc_ref = self._collection_ref().document(log.id)
        doc_ref.set(log.to_firestore_dict())
        return log

    def list_recent(self, limit: int = 10) -> list[HeartbeatLog]:
        docs = (
            self._collection_ref()
            .order_by("timestamp", direction="DESCENDING")
            .limit(limit)
            .stream()
        )
        return [
            HeartbeatLog.from_firestore_dict(doc.id, doc.to_dict())
            for doc in docs
        ]
```

- [ ] **Step 4: Implement heartbeat service**

Create `src/gclaw/heartbeat/service.py`:

```python
"""Heartbeat service — the orchestrator's consciousness loop.

The heartbeat is NOT a health monitor. It is the mechanism that makes
the orchestrator proactive. On each cycle:

1. Gather context (board state, crons, time, memories)
2. Send context to the orchestrator agent as a message
3. Let the orchestrator reason and take action (create tasks, notify, etc.)
4. Log the heartbeat result
"""

from __future__ import annotations

from gclaw.dispatch.runner import AgentRunner
from gclaw.heartbeat.context import HeartbeatContextGatherer
from gclaw.heartbeat.log import HeartbeatLog, HeartbeatLogRepo


class HeartbeatService:
    """Runs a single heartbeat cycle."""

    def __init__(
        self,
        context_gatherer: HeartbeatContextGatherer,
        agent_runner: AgentRunner,
        log_repo: HeartbeatLogRepo,
        user_id: str,
        session_id: str = "heartbeat",
    ) -> None:
        self._gatherer = context_gatherer
        self._runner = agent_runner
        self._log_repo = log_repo
        self._user_id = user_id
        self._session_id = session_id

    async def run(self) -> dict:
        """Execute one heartbeat cycle.

        Returns a dict with:
        - orchestrator_response: the agent's text response
        - actions_taken: list of tool calls the agent made
        - context: the raw context dict
        """
        # 1. Gather context
        context = self._gatherer.gather()
        message = self._gatherer.gather_as_message()

        # 2. Send to orchestrator for reasoning
        response = await self._runner.run(
            user_id=self._user_id,
            session_id=self._session_id,
            message=message,
        )

        # 3. Extract actions
        actions_taken = [
            f"{tc['name']}({tc['args']})" for tc in response.tool_calls
        ]
        tasks_created = [
            tc["args"].get("title", "unknown")
            for tc in response.tool_calls
            if tc["name"] == "create_board_task"
        ]

        # 4. Build context summary for the log
        summary = self._build_context_summary(context)

        # 5. Log the heartbeat
        log = HeartbeatLog(
            context_summary=summary,
            reasoning=response.text,
            actions_taken=actions_taken,
            tasks_created=tasks_created,
        )
        self._log_repo.save(log)

        return {
            "orchestrator_response": response.text,
            "actions_taken": actions_taken,
            "tasks_created": tasks_created,
            "context": context,
        }

    def _build_context_summary(self, context: dict) -> str:
        """Build a concise summary string from the context dict."""
        bs = context["board_summary"]
        parts = [
            f"{bs['total_tasks']} tasks on board",
            f"({bs['queued']} queued, {bs['in_progress']} in progress, "
            f"{bs['failed']} failed, {bs['needs_approval']} needs approval)",
        ]
        return " ".join(parts)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_heartbeat_log.py tests/test_heartbeat_service.py -v`
Expected: All 8 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/gclaw/heartbeat/log.py src/gclaw/heartbeat/service.py tests/test_heartbeat_log.py tests/test_heartbeat_service.py
git commit -m "feat: heartbeat service with context-driven orchestrator reasoning and logging"
```

---

### Task 7: Heartbeat Trigger Endpoint

**Files:**
- Modify: `src/gclaw/api/heartbeat_routes.py` (replace placeholder)
- Create: `tests/test_heartbeat_routes.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_heartbeat_routes.py`:

```python
"""Tests for heartbeat API endpoint."""

import pytest
from unittest.mock import MagicMock, AsyncMock
from httpx import AsyncClient, ASGITransport

from gclaw.api.app import create_app
from gclaw.dispatch.runner import AgentResponse


@pytest.fixture
def board_service():
    svc = MagicMock()
    svc.get_all_tasks.return_value = []
    return svc


@pytest.fixture
def agent_runner():
    return AsyncMock()


@pytest.fixture
def cron_service():
    return MagicMock()


@pytest.fixture
def heartbeat_service():
    svc = AsyncMock()
    svc.run.return_value = {
        "orchestrator_response": "All quiet. Nothing to do.",
        "actions_taken": [],
        "tasks_created": [],
        "context": {
            "current_time": "2026-03-30T12:00:00+00:00",
            "board_summary": {
                "total_tasks": 0,
                "backlog": 0,
                "queued": 0,
                "in_progress": 0,
                "needs_approval": 0,
                "done": 0,
                "failed": 0,
            },
            "failed_tasks": [],
            "pending_approvals": [],
            "stale_tasks": [],
            "cron_summary": {"total_crons": 0},
            "memories": [],
        },
    }
    return svc


@pytest.fixture
def app(board_service, agent_runner, cron_service, heartbeat_service):
    return create_app(
        board_service=board_service,
        agent_runner=agent_runner,
        cron_service=cron_service,
        heartbeat_service=heartbeat_service,
    )


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_trigger_heartbeat(client, heartbeat_service):
    resp = await client.post("/heartbeat")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert "orchestrator_response" in data
    heartbeat_service.run.assert_called_once()


@pytest.mark.asyncio
async def test_trigger_heartbeat_with_actions(client, heartbeat_service):
    heartbeat_service.run.return_value = {
        "orchestrator_response": "Retrying failed task t3.",
        "actions_taken": ["create_board_task({'title': 'Retry: t3', 'assignee': 'dev-mgr'})"],
        "tasks_created": ["Retry: t3"],
        "context": {"board_summary": {"total_tasks": 2}},
    }

    resp = await client.post("/heartbeat")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert len(data["actions_taken"]) == 1
    assert len(data["tasks_created"]) == 1


@pytest.mark.asyncio
async def test_trigger_heartbeat_error(client, heartbeat_service):
    heartbeat_service.run.side_effect = RuntimeError("Agent failed")
    resp = await client.post("/heartbeat")
    assert resp.status_code == 500
    data = resp.json()
    assert "error" in data["detail"].lower() or "failed" in data["detail"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_heartbeat_routes.py -v`
Expected: FAIL — the placeholder `heartbeat_routes.py` has no actual endpoint.

- [ ] **Step 3: Implement heartbeat trigger endpoint**

Replace `src/gclaw/api/heartbeat_routes.py`:

```python
"""Heartbeat trigger endpoint.

Cloud Scheduler hits POST /heartbeat to wake the orchestrator's
consciousness loop. This is not a health check — it triggers the
orchestrator to scan the world state and decide what to do.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from gclaw.heartbeat.service import HeartbeatService

router = APIRouter()

_heartbeat_service: HeartbeatService | None = None


def init_heartbeat_router(heartbeat_service: HeartbeatService) -> APIRouter:
    global _heartbeat_service
    _heartbeat_service = heartbeat_service
    return router


@router.post("/heartbeat")
async def trigger_heartbeat():
    """Trigger a heartbeat cycle.

    Called by Cloud Scheduler at a configurable interval (default: 15 min).
    The orchestrator gathers context, reasons about what needs attention,
    and takes action (create tasks, notify user, or go back to sleep).
    """
    try:
        result = await _heartbeat_service.run()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Heartbeat failed: {str(e)}",
        )

    return {
        "status": "completed",
        "orchestrator_response": result["orchestrator_response"],
        "actions_taken": result["actions_taken"],
        "tasks_created": result["tasks_created"],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_heartbeat_routes.py -v`
Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/gclaw/api/heartbeat_routes.py tests/test_heartbeat_routes.py
git commit -m "feat: heartbeat trigger endpoint for Cloud Scheduler integration"
```

---

### Task 8: Settings Update, Default Config & Full Verification

**Files:**
- Modify: `src/gclaw/settings.py`
- Create: `crons/heartbeat.json`
- No new test files — run the full suite

- [ ] **Step 1: Add heartbeat settings**

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


def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 2: Create default heartbeat config**

Create `crons/heartbeat.json`:

```json
{
    "name": "heartbeat",
    "description": "Orchestrator consciousness loop — wakes periodically to scan board state, check for stale/failed tasks, and take proactive action.",
    "interval_minutes": 15,
    "context_sources": [
        "board_scan",
        "cron_check",
        "time_check"
    ],
    "future_context_sources": [
        "memory_bank",
        "calendar",
        "email",
        "notifications"
    ],
    "notes": "Cloud Scheduler should be configured to hit POST /heartbeat every interval_minutes. Infrastructure setup is manual or via Terraform — not managed by this application."
}
```

- [ ] **Step 3: Run the complete test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All tests PASS (approximately 45+ tests across 15 test files).

- [ ] **Step 4: Check for import issues across all new modules**

Run: `python -c "from gclaw.models.cron import Cron, CronMode, CronStatus; from gclaw.firestore.cron_repo import CronRepo; from gclaw.cron.service import CronService; from gclaw.heartbeat.context import HeartbeatContextGatherer; from gclaw.heartbeat.service import HeartbeatService; from gclaw.heartbeat.log import HeartbeatLog, HeartbeatLogRepo; from gclaw.api.cron_routes import init_cron_router; from gclaw.api.heartbeat_routes import init_heartbeat_router; print('All Plan 2 imports OK')"`
Expected: "All Plan 2 imports OK"

- [ ] **Step 5: Verify existing Plan 1 tests still pass**

Run: `pytest tests/test_api.py tests/test_board_service.py tests/test_board_repo.py tests/test_models.py -v`
Expected: All Plan 1 tests PASS unchanged (backward compatible).

- [ ] **Step 6: Final commit if any fixes were needed**

```bash
git add -A
git commit -m "feat: cron system and heartbeat consciousness loop — Plan 2 complete"
```

Only commit if there were actual changes. Skip if all tests passed clean.
