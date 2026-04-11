# GClaw Foundation Implementation Plan (Plan 1 of 4)

> **STATUS: shipped 2026-03-30 → 2026-03-31** — scaffolding, board models/repo/service, agent factory, orchestrator, agent runner, FastAPI app, Cloud Run Dockerfile all landed in commits `0a69789..c49dea8`. Archived 2026-04-11.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the core backend infrastructure — project scaffolding, Firestore data layer, ADK agent framework with soul/agent.md loading, kanban project board, orchestrator routing, and Cloud Run API.

**Architecture:** Python backend using Google ADK for agent execution, FastAPI for the HTTP layer, Firestore for state management. The orchestration layer sits above ADK — it loads config files (soul/*.md, agents/*.md), assembles system prompts, creates ADK agents, and dispatches work via the kanban board. Cloud Run serves the API.

**Tech Stack:** Python 3.12, google-adk, FastAPI, google-cloud-firestore, Pydantic, pytest, Docker, Cloud Run

**Subsequent Plans:**
- Plan 2: Cron system + heartbeat consciousness loop
- Plan 3: Vertex AI Memory Bank + session compaction + skill system
- Plan 4: Next.js web app + voice + auth + multi-user A2A

---

## File Structure

```
gclaw/
├── pyproject.toml
├── Dockerfile
├── .env.example
├── soul/
│   └── base.md                          # Default soul template
├── agents/
│   ├── orchestrator.md                  # Orchestrator agent definition
│   └── workspace-mgr.md                # Workspace manager definition
├── src/
│   └── gclaw/
│       ├── __init__.py
│       ├── settings.py                  # App config via env vars
│       ├── config/
│       │   ├── __init__.py
│       │   └── loader.py               # Load & merge soul/agent.md files
│       ├── models/
│       │   ├── __init__.py
│       │   └── task.py                 # Board task Pydantic models
│       ├── firestore/
│       │   ├── __init__.py
│       │   ├── client.py               # Firestore client singleton
│       │   └── board_repo.py           # Board task CRUD on Firestore
│       ├── board/
│       │   ├── __init__.py
│       │   └── service.py             # Board business logic
│       ├── agents/
│       │   ├── __init__.py
│       │   ├── factory.py             # Build ADK agents from config
│       │   └── orchestrator.py        # Orchestrator agent + tools
│       ├── dispatch/
│       │   ├── __init__.py
│       │   └── runner.py              # Run an agent turn via ADK Runner
│       └── api/
│           ├── __init__.py
│           ├── app.py                 # FastAPI app factory
│           ├── chat.py                # POST /chat endpoint
│           └── board_routes.py        # Board CRUD endpoints
├── tests/
│   ├── conftest.py
│   ├── test_config_loader.py
│   ├── test_models.py
│   ├── test_board_repo.py
│   ├── test_board_service.py
│   ├── test_agent_factory.py
│   ├── test_orchestrator.py
│   ├── test_dispatcher.py
│   └── test_api.py
└── docs/
    └── superpowers/
        ├── specs/
        │   └── 2026-03-30-gclaw-design.md
        └── plans/
            └── 2026-03-30-gclaw-foundation.md
```

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `src/gclaw/__init__.py`
- Create: `src/gclaw/settings.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "gclaw"
version = "0.1.0"
description = "Personal AI agent platform on Google stack"
requires-python = ">=3.12"
dependencies = [
    "google-adk>=1.0.0",
    "google-cloud-firestore>=2.19.0",
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.34.0",
    "pydantic>=2.10.0",
    "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "httpx>=0.28.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/gclaw"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
pythonpath = ["src"]
```

- [ ] **Step 2: Create .env.example**

```
GCP_PROJECT_ID=your-project-id
GCP_LOCATION=us-central1
GEMINI_PRO_MODEL=gemini-2.5-flash
GEMINI_FLASH_MODEL=gemini-2.5-flash
FIRESTORE_DATABASE=(default)
```

- [ ] **Step 3: Create src/gclaw/__init__.py**

```python
"""GClaw — Personal AI agent platform on Google stack."""
```

- [ ] **Step 4: Create src/gclaw/settings.py**

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


def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 5: Create tests/conftest.py**

```python
"""Shared test fixtures."""

import os
import pytest
from gclaw.settings import Settings


@pytest.fixture
def settings(tmp_path):
    """Settings pointing at a temporary config directory."""
    os.environ["GCP_PROJECT_ID"] = "test-project"
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return Settings(
        gcp_project_id="test-project",
        gcp_location="us-central1",
        gemini_pro_model="gemini-2.5-flash",
        gemini_flash_model="gemini-2.5-flash",
        firestore_database="(default)",
        config_dir=str(config_dir),
    )
```

- [ ] **Step 6: Install dependencies and verify**

Run: `cd /mnt/c/Dev/GClaw && pip install -e ".[dev]"`
Expected: Successful install with all dependencies resolved.

- [ ] **Step 7: Run empty test suite**

Run: `pytest --co -q`
Expected: "no tests ran" with exit code 5 (no tests collected yet).

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .env.example src/ tests/conftest.py
git commit -m "feat: project scaffolding with settings and test fixtures"
```

---

### Task 2: Board Task Models

**Files:**
- Create: `src/gclaw/models/__init__.py`
- Create: `src/gclaw/models/task.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_models.py`:

```python
"""Tests for board task models."""

import pytest
from datetime import datetime, timezone
from gclaw.models.task import (
    BoardTask,
    TaskStatus,
    TaskPriority,
    TaskSource,
    TaskSourceType,
    CronConfig,
    CronMode,
    TaskResult,
    Attachment,
)


def test_create_minimal_task():
    task = BoardTask(
        title="Test task",
        assignee="workspace-mgr",
    )
    assert task.title == "Test task"
    assert task.assignee == "workspace-mgr"
    assert task.status == TaskStatus.BACKLOG
    assert task.priority == TaskPriority.MEDIUM
    assert task.source == TaskSource(type=TaskSourceType.USER)
    assert task.id is not None
    assert task.created_at is not None


def test_create_full_task():
    task = BoardTask(
        title="Schedule meeting",
        description="Book 30min with Sarah",
        status=TaskStatus.QUEUED,
        priority=TaskPriority.HIGH,
        source=TaskSource(type=TaskSourceType.AGENT, origin="research-mgr"),
        assignee="workspace-mgr",
        dependencies=["task_xyz"],
        attachments=[Attachment(type="artifact", ref="artifacts/agenda.md")],
        requires_approval=True,
        cron=CronConfig(schedule="0 8 * * MON", mode=CronMode.AUTO),
    )
    assert task.status == TaskStatus.QUEUED
    assert task.source.origin == "research-mgr"
    assert task.cron.mode == CronMode.AUTO
    assert len(task.attachments) == 1


def test_task_to_firestore_dict():
    task = BoardTask(title="Test", assignee="dev-mgr")
    d = task.to_firestore_dict()
    assert d["title"] == "Test"
    assert d["assignee"] == "dev-mgr"
    assert "id" not in d  # id is the doc key, not a field


def test_task_from_firestore_dict():
    now = datetime.now(timezone.utc)
    d = {
        "title": "From Firestore",
        "description": "",
        "status": "queued",
        "priority": "high",
        "source": {"type": "cron", "origin": "morning-briefing"},
        "assignee": "workspace-mgr",
        "dependencies": [],
        "attachments": [],
        "requires_approval": False,
        "cron": None,
        "result": None,
        "created_at": now,
        "updated_at": now,
    }
    task = BoardTask.from_firestore_dict("task_123", d)
    assert task.id == "task_123"
    assert task.status == TaskStatus.QUEUED
    assert task.source.type == TaskSourceType.CRON


def test_task_complete():
    task = BoardTask(title="Test", assignee="dev-mgr", status=TaskStatus.IN_PROGRESS)
    completed = task.complete(
        TaskResult(summary="Done", artifacts=["out.txt"])
    )
    assert completed.status == TaskStatus.DONE
    assert completed.result.summary == "Done"


def test_invalid_status_transition():
    task = BoardTask(title="Test", assignee="dev-mgr", status=TaskStatus.DONE)
    with pytest.raises(ValueError, match="Cannot transition"):
        task.transition_to(TaskStatus.BACKLOG)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gclaw.models.task'`

- [ ] **Step 3: Create models/__init__.py**

```python
"""Data models for GClaw."""
```

- [ ] **Step 4: Implement task models**

Create `src/gclaw/models/task.py`:

```python
"""Board task models for the kanban project board."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field


class TaskStatus(StrEnum):
    BACKLOG = "backlog"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    NEEDS_APPROVAL = "needs_approval"
    DONE = "done"
    FAILED = "failed"


# Valid forward transitions
_VALID_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.BACKLOG: {TaskStatus.QUEUED, TaskStatus.IN_PROGRESS},
    TaskStatus.QUEUED: {TaskStatus.IN_PROGRESS, TaskStatus.BACKLOG},
    TaskStatus.IN_PROGRESS: {
        TaskStatus.DONE,
        TaskStatus.FAILED,
        TaskStatus.NEEDS_APPROVAL,
    },
    TaskStatus.NEEDS_APPROVAL: {
        TaskStatus.IN_PROGRESS,
        TaskStatus.DONE,
        TaskStatus.FAILED,
    },
    TaskStatus.FAILED: {TaskStatus.QUEUED, TaskStatus.BACKLOG},
    TaskStatus.DONE: set(),
}


class TaskPriority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TaskSourceType(StrEnum):
    USER = "user"
    AGENT = "agent"
    CRON = "cron"


class CronMode(StrEnum):
    AUTO = "auto"
    TODO = "todo"


class TaskSource(BaseModel):
    type: TaskSourceType = TaskSourceType.USER
    origin: str | None = None


class CronConfig(BaseModel):
    schedule: str
    mode: CronMode = CronMode.TODO


class Attachment(BaseModel):
    type: str
    ref: str


class TaskResult(BaseModel):
    summary: str
    artifacts: list[str] = Field(default_factory=list)


class BoardTask(BaseModel):
    id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:12]}")
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.BACKLOG
    priority: TaskPriority = TaskPriority.MEDIUM
    source: TaskSource = Field(default_factory=TaskSource)
    assignee: str = ""
    dependencies: list[str] = Field(default_factory=list)
    attachments: list[Attachment] = Field(default_factory=list)
    requires_approval: bool = False
    cron: CronConfig | None = None
    result: TaskResult | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def transition_to(self, new_status: TaskStatus) -> Self:
        valid = _VALID_TRANSITIONS.get(self.status, set())
        if new_status not in valid:
            raise ValueError(
                f"Cannot transition from {self.status} to {new_status}. "
                f"Valid targets: {valid}"
            )
        return self.model_copy(
            update={"status": new_status, "updated_at": datetime.now(timezone.utc)}
        )

    def complete(self, result: TaskResult) -> Self:
        moved = self.transition_to(TaskStatus.DONE)
        return moved.model_copy(update={"result": result})

    def to_firestore_dict(self) -> dict:
        d = self.model_dump(mode="json")
        d.pop("id")
        return d

    @classmethod
    def from_firestore_dict(cls, doc_id: str, data: dict) -> Self:
        return cls(id=doc_id, **data)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_models.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/gclaw/models/ tests/test_models.py
git commit -m "feat: board task Pydantic models with status transitions"
```

---

### Task 3: Config Loader — Soul & Agent Definitions

**Files:**
- Create: `src/gclaw/config/__init__.py`
- Create: `src/gclaw/config/loader.py`
- Create: `soul/base.md`
- Create: `agents/orchestrator.md`
- Create: `agents/workspace-mgr.md`
- Create: `tests/test_config_loader.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_config_loader.py`:

```python
"""Tests for config loader."""

import pytest
from gclaw.config.loader import ConfigLoader


@pytest.fixture
def config_dir(tmp_path):
    soul_dir = tmp_path / "soul"
    soul_dir.mkdir()
    (soul_dir / "base.md").write_text(
        "You are a helpful assistant.\n"
        "Be concise and friendly.\n"
    )
    (soul_dir / "workspace.md").write_text(
        "For email, use a professional tone.\n"
    )
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "orchestrator.md").write_text(
        "You are the root orchestrator.\n"
        "Route tasks to the appropriate manager.\n"
    )
    (agents_dir / "workspace-mgr.md").write_text(
        "You manage Google Workspace tasks.\n"
    )
    return tmp_path


def test_load_soul_base(config_dir):
    loader = ConfigLoader(str(config_dir))
    soul = loader.load_soul("base")
    assert "helpful assistant" in soul


def test_load_soul_with_overlay(config_dir):
    loader = ConfigLoader(str(config_dir))
    soul = loader.load_soul("base", overlay="workspace")
    assert "helpful assistant" in soul
    assert "professional tone" in soul


def test_load_soul_missing_overlay_ignored(config_dir):
    loader = ConfigLoader(str(config_dir))
    soul = loader.load_soul("base", overlay="nonexistent")
    assert "helpful assistant" in soul


def test_load_agent_definition(config_dir):
    loader = ConfigLoader(str(config_dir))
    defn = loader.load_agent("orchestrator")
    assert "root orchestrator" in defn


def test_build_system_prompt(config_dir):
    loader = ConfigLoader(str(config_dir))
    prompt = loader.build_system_prompt(
        agent_name="orchestrator",
        soul_base="base",
    )
    assert "root orchestrator" in prompt
    assert "helpful assistant" in prompt


def test_build_system_prompt_with_overlay(config_dir):
    loader = ConfigLoader(str(config_dir))
    prompt = loader.build_system_prompt(
        agent_name="workspace-mgr",
        soul_base="base",
        soul_overlay="workspace",
    )
    assert "Google Workspace" in prompt
    assert "professional tone" in prompt
    assert "helpful assistant" in prompt


def test_build_system_prompt_with_memories(config_dir):
    loader = ConfigLoader(str(config_dir))
    memories = [
        "User prefers short responses.",
        "User's name is Sam.",
    ]
    prompt = loader.build_system_prompt(
        agent_name="orchestrator",
        soul_base="base",
        memories=memories,
    )
    assert "User prefers short responses." in prompt
    assert "User's name is Sam." in prompt


def test_missing_agent_raises(config_dir):
    loader = ConfigLoader(str(config_dir))
    with pytest.raises(FileNotFoundError):
        loader.load_agent("nonexistent")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config_loader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gclaw.config.loader'`

- [ ] **Step 3: Implement config loader**

Create `src/gclaw/config/__init__.py`:

```python
"""Config loading for soul and agent definitions."""
```

Create `src/gclaw/config/loader.py`:

```python
"""Load and merge soul/agent.md configuration files into system prompts."""

from __future__ import annotations

import os


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

    def __init__(self, config_dir: str) -> None:
        self._config_dir = config_dir

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

        return "\n\n---\n\n".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config_loader.py -v`
Expected: All 8 tests PASS.

- [ ] **Step 5: Create default config files**

Create `soul/base.md`:

```markdown
You are GClaw, a personal AI assistant.

## Communication Style
- Be concise and direct
- Match the user's energy and formality level
- Ask clarifying questions when intent is ambiguous
- Never fabricate information — say when you don't know

## Core Behaviors
- Proactively surface relevant information when appropriate
- Respect user preferences stored in your memory
- When creating tasks for other agents, provide clear context
- Escalate to the user when actions require approval
```

Create `agents/orchestrator.md`:

```markdown
You are the root orchestrator of GClaw, the user's personal AI agent system.

## Role
You are the single entry point for all user interaction. Your job is to understand what the user wants and either handle it directly or route it to the right manager agent.

## Capabilities
- Classify user intent and determine which domain(s) are involved
- Create tasks on the project board for manager agents
- Maintain conversational context across turns
- Handle multi-domain requests by creating multiple tasks with dependencies
- Mediate when manager agents need user clarification or approval

## Available Managers
- workspace-mgr: Google Workspace tasks (email, calendar, drive, docs)
- dev-mgr: Development workflows (GitHub, CI/CD, deployment)
- home-mgr: Smart home and IoT
- comms-mgr: Communication platforms (Slack, Discord, SMS)
- research-mgr: Web research, summarization, image generation

## Routing Rules
- If the request maps to a single domain, create one task for that manager
- If the request spans multiple domains, create tasks with dependencies
- If the request is conversational (greeting, question about yourself), handle directly
- If unsure which manager to route to, ask the user for clarification

## Tools
You have access to: create_board_task, list_board_tasks, get_board_task
```

Create `agents/workspace-mgr.md`:

```markdown
You are the Workspace Manager agent in GClaw.

## Role
You coordinate Google Workspace tasks: Gmail, Calendar, Drive, and Docs. When assigned a task via the project board, you plan the steps needed and either handle them directly or spawn specialist agents.

## Capabilities
- Draft and send emails
- Schedule and manage calendar events
- Search and organize Drive files
- Create and edit documents

## Escalation Rules
- Always escalate before sending emails to external contacts
- Escalate calendar changes that conflict with existing events
- Never delete files without user approval

## Tools
You have access to: complete_board_task, update_board_task
```

- [ ] **Step 6: Commit**

```bash
git add src/gclaw/config/ tests/test_config_loader.py soul/ agents/
git commit -m "feat: config loader for soul/agent.md files with prompt assembly"
```

---

### Task 4: Firestore Client & Board Repository

**Files:**
- Create: `src/gclaw/firestore/__init__.py`
- Create: `src/gclaw/firestore/client.py`
- Create: `src/gclaw/firestore/board_repo.py`
- Create: `tests/test_board_repo.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_board_repo.py`:

```python
"""Tests for board repository.

Uses a mock Firestore client to test CRUD without a real database.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from gclaw.models.task import (
    BoardTask,
    TaskStatus,
    TaskPriority,
    TaskSource,
    TaskSourceType,
)
from gclaw.firestore.board_repo import BoardRepo


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def repo(mock_db):
    return BoardRepo(db=mock_db, user_id="user_123")


def test_task_collection_path(repo):
    ref = repo._collection_ref()
    repo._db.collection.assert_called_with("users")


def test_create_task(repo):
    task = BoardTask(title="Test task", assignee="workspace-mgr")
    doc_ref = MagicMock()
    repo._db.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref

    repo.create(task)

    doc_ref.set.assert_called_once()
    call_data = doc_ref.set.call_args[0][0]
    assert call_data["title"] == "Test task"
    assert "id" not in call_data


def test_get_task(repo):
    doc_snap = MagicMock()
    doc_snap.exists = True
    doc_snap.id = "task_abc"
    doc_snap.to_dict.return_value = {
        "title": "Found task",
        "description": "",
        "status": "queued",
        "priority": "medium",
        "source": {"type": "user", "origin": None},
        "assignee": "dev-mgr",
        "dependencies": [],
        "attachments": [],
        "requires_approval": False,
        "cron": None,
        "result": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    repo._db.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = doc_snap

    task = repo.get("task_abc")
    assert task is not None
    assert task.title == "Found task"
    assert task.id == "task_abc"


def test_get_nonexistent_task(repo):
    doc_snap = MagicMock()
    doc_snap.exists = False
    repo._db.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = doc_snap

    task = repo.get("task_nope")
    assert task is None


def test_update_task(repo):
    task = BoardTask(
        id="task_abc",
        title="Updated",
        assignee="dev-mgr",
        status=TaskStatus.IN_PROGRESS,
    )
    doc_ref = MagicMock()
    repo._db.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref

    repo.update(task)

    doc_ref.set.assert_called_once()
    call_data = doc_ref.set.call_args[0][0]
    assert call_data["status"] == "in_progress"


def test_list_by_status(repo):
    doc1 = MagicMock()
    doc1.id = "task_1"
    doc1.to_dict.return_value = {
        "title": "Task 1",
        "description": "",
        "status": "queued",
        "priority": "medium",
        "source": {"type": "user", "origin": None},
        "assignee": "workspace-mgr",
        "dependencies": [],
        "attachments": [],
        "requires_approval": False,
        "cron": None,
        "result": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    query_mock = MagicMock()
    query_mock.stream.return_value = [doc1]
    repo._db.collection.return_value.document.return_value.collection.return_value.where.return_value = query_mock

    tasks = repo.list_by_status(TaskStatus.QUEUED)
    assert len(tasks) == 1
    assert tasks[0].title == "Task 1"


def test_list_by_assignee(repo):
    doc1 = MagicMock()
    doc1.id = "task_1"
    doc1.to_dict.return_value = {
        "title": "My Task",
        "description": "",
        "status": "queued",
        "priority": "high",
        "source": {"type": "agent", "origin": "orchestrator"},
        "assignee": "workspace-mgr",
        "dependencies": [],
        "attachments": [],
        "requires_approval": False,
        "cron": None,
        "result": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    query_mock = MagicMock()
    query_mock.stream.return_value = [doc1]
    base_query = MagicMock()
    base_query.where.return_value = query_mock
    repo._db.collection.return_value.document.return_value.collection.return_value.where.return_value = base_query

    tasks = repo.list_by_assignee("workspace-mgr")
    assert len(tasks) == 1
    assert tasks[0].assignee == "workspace-mgr"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_board_repo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gclaw.firestore'`

- [ ] **Step 3: Implement Firestore client**

Create `src/gclaw/firestore/__init__.py`:

```python
"""Firestore data access layer."""
```

Create `src/gclaw/firestore/client.py`:

```python
"""Firestore client singleton."""

from __future__ import annotations

from google.cloud import firestore

_client: firestore.Client | None = None


def get_firestore_client(
    project: str | None = None,
    database: str = "(default)",
) -> firestore.Client:
    global _client
    if _client is None:
        _client = firestore.Client(project=project, database=database)
    return _client
```

- [ ] **Step 4: Implement board repository**

Create `src/gclaw/firestore/board_repo.py`:

```python
"""Board task CRUD operations on Firestore.

Collection path: users/{userId}/board/{taskId}
"""

from __future__ import annotations

from google.cloud.firestore import Client as FirestoreClient

from gclaw.models.task import BoardTask, TaskStatus


class BoardRepo:
    """Synchronous Firestore repository for board tasks."""

    def __init__(self, db: FirestoreClient, user_id: str) -> None:
        self._db = db
        self._user_id = user_id

    def _collection_ref(self):
        return (
            self._db.collection("users")
            .document(self._user_id)
            .collection("board")
        )

    def create(self, task: BoardTask) -> BoardTask:
        doc_ref = self._collection_ref().document(task.id)
        doc_ref.set(task.to_firestore_dict())
        return task

    def get(self, task_id: str) -> BoardTask | None:
        doc = self._collection_ref().document(task_id).get()
        if not doc.exists:
            return None
        return BoardTask.from_firestore_dict(doc.id, doc.to_dict())

    def update(self, task: BoardTask) -> BoardTask:
        doc_ref = self._collection_ref().document(task.id)
        doc_ref.set(task.to_firestore_dict())
        return task

    def delete(self, task_id: str) -> None:
        self._collection_ref().document(task_id).delete()

    def list_by_status(self, status: TaskStatus) -> list[BoardTask]:
        docs = (
            self._collection_ref()
            .where("status", "==", status.value)
            .stream()
        )
        return [
            BoardTask.from_firestore_dict(doc.id, doc.to_dict()) for doc in docs
        ]

    def list_by_assignee(
        self, assignee: str, status: TaskStatus | None = None
    ) -> list[BoardTask]:
        query = self._collection_ref().where("assignee", "==", assignee)
        if status:
            query = query.where("status", "==", status.value)
        docs = query.stream()
        return [
            BoardTask.from_firestore_dict(doc.id, doc.to_dict()) for doc in docs
        ]

    def list_all(self) -> list[BoardTask]:
        docs = self._collection_ref().stream()
        return [
            BoardTask.from_firestore_dict(doc.id, doc.to_dict()) for doc in docs
        ]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_board_repo.py -v`
Expected: All 7 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/gclaw/firestore/ tests/test_board_repo.py
git commit -m "feat: Firestore board repository with task CRUD"
```

---

### Task 5: Board Service — Business Logic

**Files:**
- Create: `src/gclaw/board/__init__.py`
- Create: `src/gclaw/board/service.py`
- Create: `tests/test_board_service.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_board_service.py`:

```python
"""Tests for board service business logic."""

import pytest
from unittest.mock import MagicMock

from gclaw.models.task import (
    BoardTask,
    TaskStatus,
    TaskSource,
    TaskSourceType,
    TaskResult,
)
from gclaw.board.service import BoardService


@pytest.fixture
def repo():
    return MagicMock()


@pytest.fixture
def service(repo):
    return BoardService(repo=repo)


def test_create_task_from_user(service, repo):
    repo.create.side_effect = lambda t: t
    task = service.create_task(
        title="Do the thing",
        assignee="workspace-mgr",
        source_type="user",
    )
    assert task.title == "Do the thing"
    assert task.source.type == TaskSourceType.USER
    assert task.status == TaskStatus.BACKLOG
    repo.create.assert_called_once()


def test_create_task_from_agent(service, repo):
    repo.create.side_effect = lambda t: t
    task = service.create_task(
        title="Subtask",
        assignee="workspace-mgr",
        source_type="agent",
        source_origin="research-mgr",
        status=TaskStatus.QUEUED,
    )
    assert task.source.type == TaskSourceType.AGENT
    assert task.source.origin == "research-mgr"
    assert task.status == TaskStatus.QUEUED


def test_pick_up_task(service, repo):
    task = BoardTask(
        id="task_1",
        title="Queued task",
        assignee="workspace-mgr",
        status=TaskStatus.QUEUED,
    )
    repo.get.return_value = task
    repo.update.side_effect = lambda t: t

    picked = service.pick_up("task_1")
    assert picked.status == TaskStatus.IN_PROGRESS
    repo.update.assert_called_once()


def test_pick_up_nonexistent_raises(service, repo):
    repo.get.return_value = None
    with pytest.raises(ValueError, match="not found"):
        service.pick_up("nope")


def test_complete_task(service, repo):
    task = BoardTask(
        id="task_1",
        title="In progress task",
        assignee="dev-mgr",
        status=TaskStatus.IN_PROGRESS,
    )
    repo.get.return_value = task
    repo.update.side_effect = lambda t: t

    completed = service.complete(
        "task_1", summary="All done", artifacts=["out.txt"]
    )
    assert completed.status == TaskStatus.DONE
    assert completed.result.summary == "All done"


def test_fail_task(service, repo):
    task = BoardTask(
        id="task_1",
        title="Failing task",
        assignee="dev-mgr",
        status=TaskStatus.IN_PROGRESS,
    )
    repo.get.return_value = task
    repo.update.side_effect = lambda t: t

    failed = service.fail("task_1", reason="API timeout")
    assert failed.status == TaskStatus.FAILED
    assert failed.result.summary == "API timeout"


def test_get_pending_tasks_for_agent(service, repo):
    tasks = [
        BoardTask(id="t1", title="T1", assignee="workspace-mgr", status=TaskStatus.QUEUED),
    ]
    repo.list_by_assignee.return_value = tasks

    result = service.get_pending_tasks("workspace-mgr")
    assert len(result) == 1
    repo.list_by_assignee.assert_called_with("workspace-mgr", status=TaskStatus.QUEUED)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_board_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gclaw.board'`

- [ ] **Step 3: Implement board service**

Create `src/gclaw/board/__init__.py`:

```python
"""Board business logic."""
```

Create `src/gclaw/board/service.py`:

```python
"""Board service — business logic for kanban task management."""

from __future__ import annotations

from gclaw.firestore.board_repo import BoardRepo
from gclaw.models.task import (
    BoardTask,
    TaskPriority,
    TaskResult,
    TaskSource,
    TaskSourceType,
    TaskStatus,
)


class BoardService:
    """High-level operations on the project board."""

    def __init__(self, repo: BoardRepo) -> None:
        self._repo = repo

    def create_task(
        self,
        title: str,
        assignee: str,
        source_type: str = "user",
        source_origin: str | None = None,
        description: str = "",
        priority: TaskPriority = TaskPriority.MEDIUM,
        status: TaskStatus = TaskStatus.BACKLOG,
        dependencies: list[str] | None = None,
        requires_approval: bool = False,
    ) -> BoardTask:
        task = BoardTask(
            title=title,
            description=description,
            status=status,
            priority=priority,
            source=TaskSource(
                type=TaskSourceType(source_type),
                origin=source_origin,
            ),
            assignee=assignee,
            dependencies=dependencies or [],
            requires_approval=requires_approval,
        )
        return self._repo.create(task)

    def pick_up(self, task_id: str) -> BoardTask:
        task = self._repo.get(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        updated = task.transition_to(TaskStatus.IN_PROGRESS)
        return self._repo.update(updated)

    def complete(
        self,
        task_id: str,
        summary: str,
        artifacts: list[str] | None = None,
    ) -> BoardTask:
        task = self._repo.get(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        completed = task.complete(TaskResult(
            summary=summary, artifacts=artifacts or []
        ))
        return self._repo.update(completed)

    def fail(self, task_id: str, reason: str) -> BoardTask:
        task = self._repo.get(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        failed = task.transition_to(TaskStatus.FAILED)
        failed = failed.model_copy(
            update={"result": TaskResult(summary=reason)}
        )
        return self._repo.update(failed)

    def get_pending_tasks(self, assignee: str) -> list[BoardTask]:
        return self._repo.list_by_assignee(assignee, status=TaskStatus.QUEUED)

    def get_all_tasks(self) -> list[BoardTask]:
        return self._repo.list_all()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_board_service.py -v`
Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/gclaw/board/ tests/test_board_service.py
git commit -m "feat: board service with task lifecycle operations"
```

---

### Task 6: Agent Factory — Build ADK Agents from Config

**Files:**
- Create: `src/gclaw/agents/__init__.py`
- Create: `src/gclaw/agents/factory.py`
- Create: `tests/test_agent_factory.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_agent_factory.py`:

```python
"""Tests for agent factory."""

import pytest
from gclaw.agents.factory import AgentFactory
from gclaw.config.loader import ConfigLoader


@pytest.fixture
def config_dir(tmp_path):
    soul_dir = tmp_path / "soul"
    soul_dir.mkdir()
    (soul_dir / "base.md").write_text("You are helpful.\n")
    (soul_dir / "workspace.md").write_text("Professional email tone.\n")

    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "orchestrator.md").write_text(
        "You are the root orchestrator. Route to managers.\n"
    )
    (agents_dir / "workspace-mgr.md").write_text(
        "You manage workspace tasks.\n"
    )
    return tmp_path


@pytest.fixture
def factory(config_dir):
    loader = ConfigLoader(str(config_dir))
    return AgentFactory(loader=loader, default_model="gemini-2.5-flash")


def test_build_agent(factory):
    agent = factory.build(
        agent_name="orchestrator",
        soul_overlay=None,
    )
    assert agent.name == "orchestrator"
    assert "root orchestrator" in agent.instruction
    assert "helpful" in agent.instruction


def test_build_agent_with_overlay(factory):
    agent = factory.build(
        agent_name="workspace-mgr",
        soul_overlay="workspace",
    )
    assert agent.name == "workspace-mgr"
    assert "Professional email" in agent.instruction
    assert "helpful" in agent.instruction


def test_build_agent_with_tools(factory):
    def dummy_tool(x: str) -> str:
        """A dummy tool."""
        return x

    agent = factory.build(
        agent_name="orchestrator",
        tools=[dummy_tool],
    )
    assert len(agent.tools) == 1


def test_build_agent_with_sub_agents(factory):
    child = factory.build(agent_name="workspace-mgr", soul_overlay="workspace")
    parent = factory.build(
        agent_name="orchestrator",
        sub_agents=[child],
    )
    assert len(parent.sub_agents) == 1
    assert parent.sub_agents[0].name == "workspace-mgr"


def test_build_agent_with_memories(factory):
    agent = factory.build(
        agent_name="orchestrator",
        memories=["User likes bullet points."],
    )
    assert "bullet points" in agent.instruction
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_agent_factory.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gclaw.agents.factory'`

- [ ] **Step 3: Implement agent factory**

Create `src/gclaw/agents/__init__.py`:

```python
"""Agent creation and management."""
```

Create `src/gclaw/agents/factory.py`:

```python
"""Factory for building ADK agents from config files."""

from __future__ import annotations

from typing import Any

from google.adk.agents import LlmAgent

from gclaw.config.loader import ConfigLoader


class AgentFactory:
    """Creates ADK LlmAgent instances from soul/agent.md config files."""

    def __init__(
        self,
        loader: ConfigLoader,
        default_model: str = "gemini-2.5-flash",
    ) -> None:
        self._loader = loader
        self._default_model = default_model

    def build(
        self,
        agent_name: str,
        soul_overlay: str | None = None,
        memories: list[str] | None = None,
        tools: list[Any] | None = None,
        sub_agents: list[LlmAgent] | None = None,
        model: str | None = None,
        description: str | None = None,
    ) -> LlmAgent:
        instruction = self._loader.build_system_prompt(
            agent_name=agent_name,
            soul_base="base",
            soul_overlay=soul_overlay,
            memories=memories,
        )

        return LlmAgent(
            name=agent_name,
            model=model or self._default_model,
            instruction=instruction,
            description=description or f"GClaw agent: {agent_name}",
            tools=tools or [],
            sub_agents=sub_agents or [],
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_agent_factory.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/gclaw/agents/ tests/test_agent_factory.py
git commit -m "feat: agent factory builds ADK agents from soul/agent.md configs"
```

---

### Task 7: Orchestrator Agent with Board Tools

**Files:**
- Create: `src/gclaw/agents/orchestrator.py`
- Create: `tests/test_orchestrator.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_orchestrator.py`:

```python
"""Tests for orchestrator agent tools."""

import pytest
from unittest.mock import MagicMock

from gclaw.agents.orchestrator import (
    create_board_task_tool,
    list_board_tasks_tool,
    get_board_task_tool,
    build_orchestrator,
)
from gclaw.board.service import BoardService
from gclaw.models.task import BoardTask, TaskStatus


@pytest.fixture
def board_service():
    return MagicMock(spec=BoardService)


def test_create_board_task_tool(board_service):
    board_service.create_task.side_effect = lambda **kw: BoardTask(
        title=kw["title"], assignee=kw["assignee"]
    )
    tool_fn = create_board_task_tool(board_service)
    result = tool_fn(
        title="Send email to Sarah",
        assignee="workspace-mgr",
        description="Draft and send meeting follow-up",
        priority="high",
    )
    assert "Send email to Sarah" in result
    board_service.create_task.assert_called_once()


def test_list_board_tasks_tool(board_service):
    board_service.get_all_tasks.return_value = [
        BoardTask(id="t1", title="Task 1", assignee="dev-mgr", status=TaskStatus.QUEUED),
        BoardTask(id="t2", title="Task 2", assignee="workspace-mgr", status=TaskStatus.DONE),
    ]
    tool_fn = list_board_tasks_tool(board_service)
    result = tool_fn()
    assert "Task 1" in result
    assert "Task 2" in result


def test_get_board_task_tool(board_service):
    board_service._repo = MagicMock()
    task = BoardTask(id="t1", title="Specific task", assignee="dev-mgr", status=TaskStatus.IN_PROGRESS)

    # Mock the repo on the service
    repo_mock = MagicMock()
    repo_mock.get.return_value = task
    board_service._repo = repo_mock

    tool_fn = get_board_task_tool(board_service)
    result = tool_fn(task_id="t1")
    assert "Specific task" in result


def test_build_orchestrator(board_service, tmp_path):
    soul_dir = tmp_path / "soul"
    soul_dir.mkdir()
    (soul_dir / "base.md").write_text("You are helpful.\n")
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "orchestrator.md").write_text("You are the orchestrator.\n")

    from gclaw.config.loader import ConfigLoader
    from gclaw.agents.factory import AgentFactory

    loader = ConfigLoader(str(tmp_path))
    factory = AgentFactory(loader=loader)

    agent = build_orchestrator(factory=factory, board_service=board_service)
    assert agent.name == "orchestrator"
    assert len(agent.tools) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_orchestrator.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gclaw.agents.orchestrator'`

- [ ] **Step 3: Implement orchestrator**

Create `src/gclaw/agents/orchestrator.py`:

```python
"""Orchestrator agent definition with board tools."""

from __future__ import annotations

from typing import Callable

from google.adk.agents import LlmAgent

from gclaw.agents.factory import AgentFactory
from gclaw.board.service import BoardService
from gclaw.models.task import TaskStatus


def create_board_task_tool(board_service: BoardService) -> Callable:
    def create_board_task(
        title: str,
        assignee: str,
        description: str = "",
        priority: str = "medium",
        source_origin: str = "orchestrator",
    ) -> str:
        """Create a task on the project board for a manager agent to pick up.

        Args:
            title: Short description of what needs to be done.
            assignee: Which manager agent should handle this. One of:
                workspace-mgr, dev-mgr, home-mgr, comms-mgr, research-mgr.
            description: Detailed context for the assigned agent.
            priority: Task priority — high, medium, or low.
            source_origin: Which agent created this task.

        Returns:
            Confirmation with the created task ID and details.
        """
        task = board_service.create_task(
            title=title,
            assignee=assignee,
            description=description,
            priority=priority,
            source_type="agent",
            source_origin=source_origin,
            status=TaskStatus.QUEUED,
        )
        return (
            f"Task created: [{task.id}] '{task.title}' "
            f"assigned to {task.assignee} (priority: {task.priority})"
        )

    return create_board_task


def list_board_tasks_tool(board_service: BoardService) -> Callable:
    def list_board_tasks() -> str:
        """List all tasks currently on the project board.

        Returns:
            A formatted list of all board tasks with their status.
        """
        tasks = board_service.get_all_tasks()
        if not tasks:
            return "The board is empty — no tasks."

        lines = []
        for t in tasks:
            lines.append(
                f"- [{t.id}] {t.title} | status: {t.status} | "
                f"assignee: {t.assignee} | priority: {t.priority}"
            )
        return "\n".join(lines)

    return list_board_tasks


def get_board_task_tool(board_service: BoardService) -> Callable:
    def get_board_task(task_id: str) -> str:
        """Get details of a specific board task by ID.

        Args:
            task_id: The task ID to look up.

        Returns:
            Full task details or a not-found message.
        """
        task = board_service._repo.get(task_id)
        if task is None:
            return f"Task {task_id} not found."

        parts = [
            f"Task: {task.title}",
            f"ID: {task.id}",
            f"Status: {task.status}",
            f"Assignee: {task.assignee}",
            f"Priority: {task.priority}",
            f"Description: {task.description or '(none)'}",
            f"Source: {task.source.type} / {task.source.origin or 'user'}",
            f"Dependencies: {task.dependencies or '(none)'}",
            f"Requires approval: {task.requires_approval}",
        ]
        if task.result:
            parts.append(f"Result: {task.result.summary}")
        return "\n".join(parts)

    return get_board_task


def build_orchestrator(
    factory: AgentFactory,
    board_service: BoardService,
    memories: list[str] | None = None,
) -> LlmAgent:
    """Build the root orchestrator agent with board tools."""
    tools = [
        create_board_task_tool(board_service),
        list_board_tasks_tool(board_service),
        get_board_task_tool(board_service),
    ]

    return factory.build(
        agent_name="orchestrator",
        tools=tools,
        memories=memories,
        description=(
            "Root orchestrator — classifies user intent and routes "
            "tasks to the appropriate manager agent via the project board."
        ),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_orchestrator.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/gclaw/agents/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: orchestrator agent with board tools (create, list, get tasks)"
```

---

### Task 8: Agent Runner — Execute Agent Turns via ADK

**Files:**
- Create: `src/gclaw/dispatch/__init__.py`
- Create: `src/gclaw/dispatch/runner.py`
- Create: `tests/test_dispatcher.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_dispatcher.py`:

```python
"""Tests for agent runner."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from gclaw.dispatch.runner import AgentRunner


@pytest.fixture
def mock_session_service():
    svc = AsyncMock()
    session = MagicMock()
    session.id = "session_123"
    svc.create_session = AsyncMock(return_value=session)
    svc.get_session = AsyncMock(return_value=session)
    return svc


def test_runner_init():
    agent = MagicMock()
    agent.name = "orchestrator"
    runner = AgentRunner(
        agent=agent,
        app_name="gclaw",
        session_service=AsyncMock(),
    )
    assert runner._agent.name == "orchestrator"
    assert runner._app_name == "gclaw"


@pytest.mark.asyncio
async def test_runner_run_collects_text(mock_session_service):
    agent = MagicMock()
    agent.name = "orchestrator"

    runner = AgentRunner(
        agent=agent,
        app_name="gclaw",
        session_service=mock_session_service,
    )

    # Mock the ADK Runner
    mock_event = MagicMock()
    mock_event.is_final_response.return_value = True
    mock_part = MagicMock()
    mock_part.text = "Hello! How can I help?"
    mock_part.function_call = None
    mock_event.content = MagicMock()
    mock_event.content.parts = [mock_part]

    async def fake_run(**kwargs):
        yield mock_event

    with patch("gclaw.dispatch.runner.Runner") as MockRunner:
        instance = MockRunner.return_value
        instance.run_async = fake_run

        response = await runner.run(
            user_id="user_1",
            session_id="session_123",
            message="Hello",
        )

    assert response.text == "Hello! How can I help?"
    assert response.is_final is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dispatcher.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gclaw.dispatch'`

- [ ] **Step 3: Implement agent runner**

Create `src/gclaw/dispatch/__init__.py`:

```python
"""Agent dispatch and execution."""
```

Create `src/gclaw/dispatch/runner.py`:

```python
"""Run agent turns via ADK Runner."""

from __future__ import annotations

from dataclasses import dataclass, field

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService
from google.genai import types


@dataclass
class AgentResponse:
    """Response from a single agent turn."""

    text: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    is_final: bool = False


class AgentRunner:
    """Wraps ADK Runner for executing agent turns."""

    def __init__(
        self,
        agent: LlmAgent,
        app_name: str,
        session_service: BaseSessionService,
    ) -> None:
        self._agent = agent
        self._app_name = app_name
        self._session_service = session_service
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
        """Run a single turn: send message, collect response."""
        content = types.Content(
            role="user",
            parts=[types.Part(text=message)],
        )

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

        return response
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_dispatcher.py -v`
Expected: All 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/gclaw/dispatch/ tests/test_dispatcher.py
git commit -m "feat: agent runner wraps ADK for executing agent turns"
```

---

### Task 9: FastAPI Application — Chat & Board Endpoints

**Files:**
- Create: `src/gclaw/api/__init__.py`
- Create: `src/gclaw/api/app.py`
- Create: `src/gclaw/api/chat.py`
- Create: `src/gclaw/api/board_routes.py`
- Create: `tests/test_api.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_api.py`:

```python
"""Tests for FastAPI endpoints."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from httpx import AsyncClient, ASGITransport

from gclaw.api.app import create_app
from gclaw.models.task import BoardTask, TaskStatus


@pytest.fixture
def board_service():
    svc = MagicMock()
    svc.get_all_tasks.return_value = []
    svc.create_task.side_effect = lambda **kw: BoardTask(
        title=kw["title"], assignee=kw["assignee"]
    )
    return svc


@pytest.fixture
def agent_runner():
    runner = AsyncMock()
    return runner


@pytest.fixture
def app(board_service, agent_runner):
    return create_app(board_service=board_service, agent_runner=agent_runner)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_chat(client, agent_runner):
    from gclaw.dispatch.runner import AgentResponse

    agent_runner.run.return_value = AgentResponse(
        text="Hello! I'm GClaw.", is_final=True
    )

    resp = await client.post("/chat", json={
        "user_id": "user_1",
        "session_id": "sess_1",
        "message": "Hello",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["text"] == "Hello! I'm GClaw."
    assert data["is_final"] is True


@pytest.mark.asyncio
async def test_list_board_tasks_empty(client):
    resp = await client.get("/board/tasks", params={"user_id": "user_1"})
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_board_task(client, board_service):
    resp = await client.post("/board/tasks", json={
        "user_id": "user_1",
        "title": "New task",
        "assignee": "workspace-mgr",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "New task"
    board_service.create_task.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gclaw.api'`

- [ ] **Step 3: Implement API modules**

Create `src/gclaw/api/__init__.py`:

```python
"""FastAPI application and routes."""
```

Create `src/gclaw/api/chat.py`:

```python
"""Chat endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from gclaw.dispatch.runner import AgentRunner

router = APIRouter()

_runner: AgentRunner | None = None


def init_chat_router(runner: AgentRunner) -> APIRouter:
    global _runner
    _runner = runner
    return router


class ChatRequest(BaseModel):
    user_id: str
    session_id: str
    message: str


class ChatResponse(BaseModel):
    text: str
    tool_calls: list[dict] = []
    is_final: bool = False


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    response = await _runner.run(
        user_id=req.user_id,
        session_id=req.session_id,
        message=req.message,
    )
    return ChatResponse(
        text=response.text,
        tool_calls=response.tool_calls,
        is_final=response.is_final,
    )
```

Create `src/gclaw/api/board_routes.py`:

```python
"""Board CRUD endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from gclaw.board.service import BoardService

router = APIRouter(prefix="/board")

_board_service: BoardService | None = None


def init_board_router(board_service: BoardService) -> APIRouter:
    global _board_service
    _board_service = board_service
    return router


class CreateTaskRequest(BaseModel):
    user_id: str
    title: str
    assignee: str
    description: str = ""
    priority: str = "medium"


@router.get("/tasks")
def list_tasks(user_id: str = Query(...)):
    tasks = _board_service.get_all_tasks()
    return [t.model_dump(mode="json") for t in tasks]


@router.post("/tasks", status_code=201)
def create_task(req: CreateTaskRequest):
    task = _board_service.create_task(
        title=req.title,
        assignee=req.assignee,
        description=req.description,
        priority=req.priority,
    )
    return task.model_dump(mode="json")
```

Create `src/gclaw/api/app.py`:

```python
"""FastAPI app factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from gclaw.api.chat import init_chat_router
from gclaw.api.board_routes import init_board_router
from gclaw.board.service import BoardService
from gclaw.dispatch.runner import AgentRunner


def create_app(
    board_service: BoardService,
    agent_runner: AgentRunner,
) -> FastAPI:
    app = FastAPI(title="GClaw", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(init_chat_router(agent_runner))
    app.include_router(init_board_router(board_service))

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/gclaw/api/ tests/test_api.py
git commit -m "feat: FastAPI app with chat and board CRUD endpoints"
```

---

### Task 10: Dockerfile & Cloud Run Entry Point

**Files:**
- Create: `Dockerfile`
- Create: `src/gclaw/main.py`

- [ ] **Step 1: Create the main entry point**

Create `src/gclaw/main.py`:

```python
"""Cloud Run entry point — wires everything together and starts the server."""

from __future__ import annotations

import os

from google.adk.sessions import InMemorySessionService

from gclaw.settings import get_settings
from gclaw.config.loader import ConfigLoader
from gclaw.agents.factory import AgentFactory
from gclaw.agents.orchestrator import build_orchestrator
from gclaw.board.service import BoardService
from gclaw.dispatch.runner import AgentRunner
from gclaw.firestore.client import get_firestore_client
from gclaw.firestore.board_repo import BoardRepo
from gclaw.api.app import create_app


def build_app():
    settings = get_settings()

    # Firestore
    db = get_firestore_client(
        project=settings.gcp_project_id,
        database=settings.firestore_database,
    )

    # For now, use a hardcoded user ID — Plan 4 adds Firebase Auth
    user_id = os.environ.get("GCLAW_USER_ID", "default_user")

    # Board
    board_repo = BoardRepo(db=db, user_id=user_id)
    board_service = BoardService(repo=board_repo)

    # Config
    loader = ConfigLoader(settings.config_dir)
    factory = AgentFactory(
        loader=loader,
        default_model=settings.gemini_pro_model,
    )

    # Orchestrator
    orchestrator = build_orchestrator(
        factory=factory,
        board_service=board_service,
    )

    # Session service (in-memory for now — Plan 3 adds Firestore sessions)
    session_service = InMemorySessionService()

    # Runner
    runner = AgentRunner(
        agent=orchestrator,
        app_name="gclaw",
        session_service=session_service,
    )

    return create_app(board_service=board_service, agent_runner=runner)


app = build_app()

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
```

- [ ] **Step 2: Create Dockerfile**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/
COPY soul/ soul/
COPY agents/ agents/

RUN pip install --no-cache-dir .

ENV GCLAW_CONFIG_DIR=/app

EXPOSE 8080

CMD ["python", "-m", "gclaw.main"]
```

- [ ] **Step 3: Verify the build locally**

Run: `cd /mnt/c/Dev/GClaw && python -c "from gclaw.main import build_app; print('Import OK')"`

Note: This will fail if GCP credentials aren't configured, which is expected. The import test verifies all modules wire together correctly.

- [ ] **Step 4: Commit**

```bash
git add src/gclaw/main.py Dockerfile
git commit -m "feat: Cloud Run entry point and Dockerfile"
```

---

### Task 11: Run Full Test Suite & Verify

**Files:**
- No new files

- [ ] **Step 1: Run the complete test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All tests PASS (approximately 30+ tests across 7 test files).

- [ ] **Step 2: Check for import issues**

Run: `python -c "from gclaw.settings import get_settings; from gclaw.config.loader import ConfigLoader; from gclaw.agents.factory import AgentFactory; from gclaw.agents.orchestrator import build_orchestrator; from gclaw.board.service import BoardService; from gclaw.api.app import create_app; print('All imports OK')"`
Expected: "All imports OK"

- [ ] **Step 3: Final commit if any fixes were needed**

```bash
git add -A
git commit -m "fix: address any issues found in full test suite run"
```

Only commit if there were actual changes. Skip if all tests passed clean.
