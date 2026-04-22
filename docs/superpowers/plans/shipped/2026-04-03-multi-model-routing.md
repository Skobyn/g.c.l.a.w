# Multi-Model Routing: Gemma 4 + Nemotron on Vertex AI

> **STATUS: shipped 2026-04-03 → 2026-04-11** — model config, router, settings, admin endpoints, integration tests all landed in commits `9d7e979..6be3a2b` (merged via PR #1 `1edcb61`). LiteLlm replaced the bespoke RemoteRunner path; see sibling plan `2026-04-04-multi-provider-routing.md` for that pivot. Archived 2026-04-11.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a model routing layer to GClaw that assigns Gemini, Gemma 4, or Nemotron to each agent based on task profile, enabling tiered model selection across the agent hierarchy.

**Architecture:** A `ModelRouter` resolves model identifiers to Vertex AI endpoints. The `AgentFactory` accepts routing hints (task profiles) and delegates to `ModelRouter` for endpoint resolution. Gemma 4 and Nemotron run as Vertex AI Model Garden endpoints (managed deployment), exposed via OpenAI-compatible API. ADK's `LlmAgent` supports custom model strings pointing to Vertex AI endpoints.

**Tech Stack:** Python 3.12, google-adk, google-cloud-aiplatform, FastAPI, Pydantic, pytest

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `src/gclaw/models/model_config.py` | Pydantic models for model registry entries and routing rules |
| Create | `src/gclaw/routing/router.py` | ModelRouter — resolves task profiles to model endpoints |
| Create | `src/gclaw/routing/__init__.py` | Package init |
| Modify | `src/gclaw/settings.py` | Add model endpoint env vars and routing toggle |
| Modify | `src/gclaw/agents/factory.py` | Accept ModelRouter, resolve model per agent |
| Modify | `src/gclaw/main.py` | Wire ModelRouter into startup |
| Modify | `src/gclaw/dispatch/runner.py` | Pass routing context through to agent |
| Create | `tests/test_model_config.py` | Model config unit tests |
| Create | `tests/test_model_router.py` | Router resolution tests |
| Modify | `tests/test_agent_factory.py` | Add tests for routed model selection |
| Modify | `tests/conftest.py` | Add model routing fixtures |

---

### Task 1: Model Configuration Data Models

**Files:**
- Create: `src/gclaw/models/model_config.py`
- Create: `tests/test_model_config.py`

- [ ] **Step 1: Write the failing test for ModelEndpoint**

```python
# tests/test_model_config.py
"""Tests for model configuration models."""

from gclaw.models.model_config import ModelEndpoint, TaskProfile, RoutingRule


def test_model_endpoint_defaults():
    ep = ModelEndpoint(
        name="gemma-4-31b",
        endpoint_id="projects/your-project/locations/us-central1/endpoints/123",
    )
    assert ep.name == "gemma-4-31b"
    assert ep.provider == "vertex"
    assert ep.max_context_tokens == 0


def test_model_endpoint_with_context():
    ep = ModelEndpoint(
        name="nemotron-3-super",
        endpoint_id="projects/your-project/locations/us-central1/endpoints/456",
        max_context_tokens=1_000_000,
        provider="nim",
    )
    assert ep.max_context_tokens == 1_000_000
    assert ep.provider == "nim"


def test_task_profile_values():
    assert TaskProfile.ORCHESTRATION == "orchestration"
    assert TaskProfile.TOOL_EXECUTION == "tool_execution"
    assert TaskProfile.CODE_GENERATION == "code_generation"
    assert TaskProfile.SUMMARIZATION == "summarization"
    assert TaskProfile.PERSONALITY == "personality"
    assert TaskProfile.BACKGROUND == "background"


def test_routing_rule():
    rule = RoutingRule(
        task_profile=TaskProfile.TOOL_EXECUTION,
        model_name="nemotron-3-super",
    )
    assert rule.task_profile == TaskProfile.TOOL_EXECUTION
    assert rule.model_name == "nemotron-3-super"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /mnt/c/Dev/GClaw && python -m pytest tests/test_model_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gclaw.models.model_config'`

- [ ] **Step 3: Write the implementation**

```python
# src/gclaw/models/model_config.py
"""Data models for multi-model routing configuration."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class TaskProfile(str, Enum):
    """Task profiles that determine which model tier to use."""

    ORCHESTRATION = "orchestration"
    TOOL_EXECUTION = "tool_execution"
    CODE_GENERATION = "code_generation"
    SUMMARIZATION = "summarization"
    PERSONALITY = "personality"
    BACKGROUND = "background"


class ModelEndpoint(BaseModel):
    """A model endpoint deployed on Vertex AI or accessible via NIM."""

    name: str
    endpoint_id: str
    provider: str = "vertex"
    max_context_tokens: int = 0


class RoutingRule(BaseModel):
    """Maps a task profile to a model name."""

    task_profile: TaskProfile
    model_name: str
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /mnt/c/Dev/GClaw && python -m pytest tests/test_model_config.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/gclaw/models/model_config.py tests/test_model_config.py
git commit -m "feat: add model config data models for multi-model routing"
```

---

### Task 2: Settings — Model Endpoint Environment Variables

**Files:**
- Modify: `src/gclaw/settings.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Write the failing test**

```python
# Add to tests/conftest.py — update the existing settings fixture
# After the existing fields in the Settings() constructor, add assertions:

# In a new file tests/test_settings_models.py:
"""Tests for model routing settings."""

import os
import pytest
from gclaw.settings import Settings


def test_settings_model_routing_defaults():
    os.environ["GCP_PROJECT_ID"] = "test-project"
    s = Settings()
    assert s.model_routing_enabled is False
    assert s.gemma_endpoint_id == ""
    assert s.nemotron_endpoint_id == ""
    assert s.nemotron_provider == "vertex"


def test_settings_model_routing_enabled():
    os.environ["GCP_PROJECT_ID"] = "test-project"
    os.environ["MODEL_ROUTING_ENABLED"] = "true"
    os.environ["GEMMA_ENDPOINT_ID"] = "projects/your-project/locations/us-central1/endpoints/111"
    os.environ["NEMOTRON_ENDPOINT_ID"] = "projects/your-project/locations/us-central1/endpoints/222"
    os.environ["NEMOTRON_PROVIDER"] = "nim"
    try:
        s = Settings()
        assert s.model_routing_enabled is True
        assert "111" in s.gemma_endpoint_id
        assert "222" in s.nemotron_endpoint_id
        assert s.nemotron_provider == "nim"
    finally:
        for key in ["MODEL_ROUTING_ENABLED", "GEMMA_ENDPOINT_ID",
                     "NEMOTRON_ENDPOINT_ID", "NEMOTRON_PROVIDER"]:
            os.environ.pop(key, None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /mnt/c/Dev/GClaw && python -m pytest tests/test_settings_models.py -v`
Expected: FAIL with `AttributeError: ... has no attribute 'model_routing_enabled'`

- [ ] **Step 3: Add model routing fields to Settings**

Add the following fields to `src/gclaw/settings.py` inside the `Settings` dataclass, after the existing `skills_dir` field:

```python
    # Model routing settings
    model_routing_enabled: bool = field(
        default_factory=lambda: os.environ.get(
            "MODEL_ROUTING_ENABLED", "false"
        ).lower() == "true"
    )
    gemma_endpoint_id: str = field(
        default_factory=lambda: os.environ.get("GEMMA_ENDPOINT_ID", "")
    )
    nemotron_endpoint_id: str = field(
        default_factory=lambda: os.environ.get("NEMOTRON_ENDPOINT_ID", "")
    )
    nemotron_provider: str = field(
        default_factory=lambda: os.environ.get("NEMOTRON_PROVIDER", "vertex")
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /mnt/c/Dev/GClaw && python -m pytest tests/test_settings_models.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/gclaw/settings.py tests/test_settings_models.py
git commit -m "feat: add model routing settings (Gemma, Nemotron endpoints)"
```

---

### Task 3: ModelRouter — Core Routing Logic

**Files:**
- Create: `src/gclaw/routing/__init__.py`
- Create: `src/gclaw/routing/router.py`
- Create: `tests/test_model_router.py`

- [ ] **Step 1: Create the package init**

```python
# src/gclaw/routing/__init__.py
```

(Empty file — just makes it a package.)

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_model_router.py
"""Tests for model router."""

import pytest
from gclaw.models.model_config import ModelEndpoint, TaskProfile, RoutingRule
from gclaw.routing.router import ModelRouter


@pytest.fixture
def endpoints():
    return {
        "gemini-pro": ModelEndpoint(
            name="gemini-pro",
            endpoint_id="gemini-2.5-pro",
            max_context_tokens=1_000_000,
        ),
        "gemma-4-31b": ModelEndpoint(
            name="gemma-4-31b",
            endpoint_id="projects/your-project/locations/us-central1/endpoints/111",
            max_context_tokens=256_000,
        ),
        "nemotron-3-super": ModelEndpoint(
            name="nemotron-3-super",
            endpoint_id="projects/your-project/locations/us-central1/endpoints/222",
            max_context_tokens=1_000_000,
            provider="nim",
        ),
    }


@pytest.fixture
def rules():
    return [
        RoutingRule(task_profile=TaskProfile.ORCHESTRATION, model_name="gemini-pro"),
        RoutingRule(task_profile=TaskProfile.PERSONALITY, model_name="gemini-pro"),
        RoutingRule(task_profile=TaskProfile.TOOL_EXECUTION, model_name="nemotron-3-super"),
        RoutingRule(task_profile=TaskProfile.CODE_GENERATION, model_name="nemotron-3-super"),
        RoutingRule(task_profile=TaskProfile.SUMMARIZATION, model_name="gemma-4-31b"),
        RoutingRule(task_profile=TaskProfile.BACKGROUND, model_name="gemma-4-31b"),
    ]


@pytest.fixture
def router(endpoints, rules):
    return ModelRouter(
        endpoints=endpoints,
        rules=rules,
        default_model="gemini-2.5-flash",
    )


def test_resolve_orchestration(router):
    model_id = router.resolve(TaskProfile.ORCHESTRATION)
    assert model_id == "gemini-2.5-pro"


def test_resolve_tool_execution(router):
    model_id = router.resolve(TaskProfile.TOOL_EXECUTION)
    assert "222" in model_id


def test_resolve_summarization(router):
    model_id = router.resolve(TaskProfile.SUMMARIZATION)
    assert "111" in model_id


def test_resolve_unknown_profile_returns_default(router):
    # TaskProfile that has no rule should fall back to default
    router_no_rules = ModelRouter(
        endpoints={},
        rules=[],
        default_model="gemini-2.5-flash",
    )
    model_id = router_no_rules.resolve(TaskProfile.ORCHESTRATION)
    assert model_id == "gemini-2.5-flash"


def test_resolve_missing_endpoint_returns_default(router):
    # Rule exists but endpoint name doesn't match any registered endpoint
    bad_rules = [
        RoutingRule(task_profile=TaskProfile.ORCHESTRATION, model_name="nonexistent"),
    ]
    router_bad = ModelRouter(
        endpoints={},
        rules=bad_rules,
        default_model="gemini-2.5-flash",
    )
    model_id = router_bad.resolve(TaskProfile.ORCHESTRATION)
    assert model_id == "gemini-2.5-flash"


def test_resolve_by_agent_name(router):
    model_id = router.resolve_for_agent("orchestrator")
    assert model_id == "gemini-2.5-pro"


def test_resolve_by_agent_name_specialist(router):
    model_id = router.resolve_for_agent("code-specialist")
    assert "222" in model_id


def test_resolve_by_agent_name_unknown(router):
    model_id = router.resolve_for_agent("unknown-agent")
    assert model_id == "gemini-2.5-flash"


def test_get_endpoint_info(router):
    ep = router.get_endpoint(TaskProfile.ORCHESTRATION)
    assert ep is not None
    assert ep.name == "gemini-pro"
    assert ep.max_context_tokens == 1_000_000


def test_get_endpoint_info_missing(router):
    router_empty = ModelRouter(endpoints={}, rules=[], default_model="gemini-2.5-flash")
    ep = router_empty.get_endpoint(TaskProfile.ORCHESTRATION)
    assert ep is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /mnt/c/Dev/GClaw && python -m pytest tests/test_model_router.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gclaw.routing'`

- [ ] **Step 4: Write the ModelRouter implementation**

```python
# src/gclaw/routing/router.py
"""Model router — resolves task profiles to Vertex AI model endpoints."""

from __future__ import annotations

import logging

from gclaw.models.model_config import ModelEndpoint, RoutingRule, TaskProfile

logger = logging.getLogger(__name__)

# Maps agent name patterns to task profiles.
# The orchestrator and personality agents need frontier reasoning.
# Managers handle coordination — use mid-tier (Gemma 4).
# Specialists execute — use high-throughput (Nemotron).
AGENT_PROFILE_MAP: dict[str, TaskProfile] = {
    "orchestrator": TaskProfile.ORCHESTRATION,
    "workspace-mgr": TaskProfile.SUMMARIZATION,
    "dev-mgr": TaskProfile.CODE_GENERATION,
    "home-mgr": TaskProfile.SUMMARIZATION,
    "comms-mgr": TaskProfile.PERSONALITY,
    "research-mgr": TaskProfile.SUMMARIZATION,
}

# Suffix-based fallback for dynamically spawned specialists
SPECIALIST_SUFFIX_MAP: dict[str, TaskProfile] = {
    "code": TaskProfile.CODE_GENERATION,
    "search": TaskProfile.TOOL_EXECUTION,
    "draft": TaskProfile.PERSONALITY,
    "summarize": TaskProfile.SUMMARIZATION,
    "audit": TaskProfile.TOOL_EXECUTION,
}


class ModelRouter:
    """Resolves task profiles to model endpoint IDs for ADK agents."""

    def __init__(
        self,
        endpoints: dict[str, ModelEndpoint],
        rules: list[RoutingRule],
        default_model: str,
    ) -> None:
        self._endpoints = endpoints
        self._rules = {r.task_profile: r.model_name for r in rules}
        self._default = default_model

    def resolve(self, profile: TaskProfile) -> str:
        """Return the model ID string for a given task profile.

        Falls back to default_model if no rule or endpoint matches.
        """
        model_name = self._rules.get(profile)
        if model_name is None:
            return self._default

        endpoint = self._endpoints.get(model_name)
        if endpoint is None:
            logger.warning(
                "No endpoint registered for model %s, using default", model_name
            )
            return self._default

        return endpoint.endpoint_id

    def resolve_for_agent(self, agent_name: str) -> str:
        """Resolve the model for a named agent using the agent profile map.

        Checks exact match first, then suffix-based matching for specialists.
        """
        profile = AGENT_PROFILE_MAP.get(agent_name)
        if profile is not None:
            return self.resolve(profile)

        # Suffix-based matching for specialists (e.g., "code-specialist")
        for suffix, prof in SPECIALIST_SUFFIX_MAP.items():
            if suffix in agent_name:
                return self.resolve(prof)

        return self._default

    def get_endpoint(self, profile: TaskProfile) -> ModelEndpoint | None:
        """Return the full endpoint info for a task profile, or None."""
        model_name = self._rules.get(profile)
        if model_name is None:
            return None
        return self._endpoints.get(model_name)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /mnt/c/Dev/GClaw && python -m pytest tests/test_model_router.py -v`
Expected: PASS (10 tests)

- [ ] **Step 6: Commit**

```bash
git add src/gclaw/routing/__init__.py src/gclaw/routing/router.py tests/test_model_router.py
git commit -m "feat: add ModelRouter for task-profile-based model selection"
```

---

### Task 4: Integrate ModelRouter into AgentFactory

**Files:**
- Modify: `src/gclaw/agents/factory.py`
- Modify: `tests/test_agent_factory.py`

- [ ] **Step 1: Write the failing tests**

Add these tests to the bottom of `tests/test_agent_factory.py`:

```python
from unittest.mock import MagicMock
from gclaw.models.model_config import ModelEndpoint, TaskProfile, RoutingRule
from gclaw.routing.router import ModelRouter


@pytest.fixture
def model_router():
    endpoints = {
        "gemini-pro": ModelEndpoint(
            name="gemini-pro",
            endpoint_id="gemini-2.5-pro",
            max_context_tokens=1_000_000,
        ),
        "nemotron-3-super": ModelEndpoint(
            name="nemotron-3-super",
            endpoint_id="projects/your-project/locations/us-central1/endpoints/222",
            max_context_tokens=1_000_000,
            provider="nim",
        ),
    }
    rules = [
        RoutingRule(task_profile=TaskProfile.ORCHESTRATION, model_name="gemini-pro"),
        RoutingRule(task_profile=TaskProfile.CODE_GENERATION, model_name="nemotron-3-super"),
    ]
    return ModelRouter(endpoints=endpoints, rules=rules, default_model="gemini-2.5-flash")


def test_build_agent_with_router(config_dir, model_router):
    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(
        loader=loader,
        default_model="gemini-2.5-flash",
        model_router=model_router,
    )
    agent = factory.build(agent_name="orchestrator")
    assert agent.model == "gemini-2.5-pro"


def test_build_agent_explicit_model_overrides_router(config_dir, model_router):
    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(
        loader=loader,
        default_model="gemini-2.5-flash",
        model_router=model_router,
    )
    agent = factory.build(agent_name="orchestrator", model="custom-model-id")
    assert agent.model == "custom-model-id"


def test_build_agent_without_router_uses_default(config_dir):
    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(loader=loader, default_model="gemini-2.5-flash")
    agent = factory.build(agent_name="orchestrator")
    assert agent.model == "gemini-2.5-flash"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/c/Dev/GClaw && python -m pytest tests/test_agent_factory.py -v`
Expected: FAIL with `TypeError: AgentFactory.__init__() got an unexpected keyword argument 'model_router'`

- [ ] **Step 3: Update AgentFactory to accept ModelRouter**

Replace the full contents of `src/gclaw/agents/factory.py`:

```python
"""Factory for building ADK agents from config files."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from google.adk.agents import LlmAgent

from gclaw.config.loader import ConfigLoader

if TYPE_CHECKING:
    from gclaw.routing.router import ModelRouter


class AgentFactory:
    """Creates ADK LlmAgent instances from soul/agent.md config files."""

    def __init__(
        self,
        loader: ConfigLoader,
        default_model: str = "gemini-2.5-flash",
        model_router: ModelRouter | None = None,
    ) -> None:
        self._loader = loader
        self._default_model = default_model
        self._router = model_router

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

        # Model resolution priority: explicit > router > default
        resolved_model = model
        if resolved_model is None and self._router is not None:
            resolved_model = self._router.resolve_for_agent(agent_name)
        if resolved_model is None:
            resolved_model = self._default_model

        safe_name = agent_name.replace("-", "_")
        return LlmAgent(
            name=safe_name,
            model=resolved_model,
            instruction=instruction,
            description=description or f"GClaw agent: {agent_name}",
            tools=tools or [],
            sub_agents=sub_agents or [],
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /mnt/c/Dev/GClaw && python -m pytest tests/test_agent_factory.py -v`
Expected: PASS (all tests including new ones)

- [ ] **Step 5: Commit**

```bash
git add src/gclaw/agents/factory.py tests/test_agent_factory.py
git commit -m "feat: integrate ModelRouter into AgentFactory for per-agent model selection"
```

---

### Task 5: Wire ModelRouter into Application Startup

**Files:**
- Modify: `src/gclaw/main.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_main_routing.py
"""Tests for model routing wiring in main."""

import os
import pytest
from unittest.mock import patch, MagicMock


def test_build_app_without_routing():
    """App builds successfully with routing disabled (default)."""
    os.environ["GCP_PROJECT_ID"] = "test-project"
    os.environ["MODEL_ROUTING_ENABLED"] = "false"
    with patch("gclaw.main.get_firestore_client") as mock_db, \
         patch("gclaw.main.InMemorySessionService"):
        mock_db.return_value = MagicMock()
        from gclaw.main import build_app
        app = build_app()
        assert app is not None


def test_build_app_with_routing():
    """App builds successfully with routing enabled and endpoints configured."""
    os.environ["GCP_PROJECT_ID"] = "test-project"
    os.environ["MODEL_ROUTING_ENABLED"] = "true"
    os.environ["GEMMA_ENDPOINT_ID"] = "projects/test/locations/us-central1/endpoints/111"
    os.environ["NEMOTRON_ENDPOINT_ID"] = "projects/test/locations/us-central1/endpoints/222"
    try:
        with patch("gclaw.main.get_firestore_client") as mock_db, \
             patch("gclaw.main.InMemorySessionService"):
            mock_db.return_value = MagicMock()
            from gclaw.main import build_app
            app = build_app()
            assert app is not None
    finally:
        for key in ["MODEL_ROUTING_ENABLED", "GEMMA_ENDPOINT_ID",
                     "NEMOTRON_ENDPOINT_ID"]:
            os.environ.pop(key, None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /mnt/c/Dev/GClaw && python -m pytest tests/test_main_routing.py -v`
Expected: FAIL (build_app doesn't handle routing yet — but may pass if routing fields just aren't used. The real validation is in step 4.)

- [ ] **Step 3: Update main.py to wire ModelRouter**

Replace the full contents of `src/gclaw/main.py`:

```python
"""Cloud Run entry point — wires everything together and starts the server."""

from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)


def _build_model_router(settings):
    """Build a ModelRouter from settings, or return None if disabled."""
    if not settings.model_routing_enabled:
        return None

    from gclaw.models.model_config import ModelEndpoint, TaskProfile, RoutingRule
    from gclaw.routing.router import ModelRouter

    endpoints: dict[str, ModelEndpoint] = {
        "gemini-pro": ModelEndpoint(
            name="gemini-pro",
            endpoint_id=settings.gemini_pro_model,
            max_context_tokens=1_000_000,
        ),
    }

    rules: list[RoutingRule] = [
        RoutingRule(task_profile=TaskProfile.ORCHESTRATION, model_name="gemini-pro"),
        RoutingRule(task_profile=TaskProfile.PERSONALITY, model_name="gemini-pro"),
    ]

    # Register Gemma 4 endpoint if configured
    if settings.gemma_endpoint_id:
        endpoints["gemma-4"] = ModelEndpoint(
            name="gemma-4",
            endpoint_id=settings.gemma_endpoint_id,
            max_context_tokens=256_000,
        )
        rules.extend([
            RoutingRule(task_profile=TaskProfile.SUMMARIZATION, model_name="gemma-4"),
            RoutingRule(task_profile=TaskProfile.BACKGROUND, model_name="gemma-4"),
        ])
        logger.info("Gemma 4 endpoint registered: %s", settings.gemma_endpoint_id)

    # Register Nemotron endpoint if configured
    if settings.nemotron_endpoint_id:
        endpoints["nemotron-3-super"] = ModelEndpoint(
            name="nemotron-3-super",
            endpoint_id=settings.nemotron_endpoint_id,
            max_context_tokens=1_000_000,
            provider=settings.nemotron_provider,
        )
        rules.extend([
            RoutingRule(task_profile=TaskProfile.TOOL_EXECUTION, model_name="nemotron-3-super"),
            RoutingRule(task_profile=TaskProfile.CODE_GENERATION, model_name="nemotron-3-super"),
        ])
        logger.info("Nemotron 3 Super endpoint registered: %s", settings.nemotron_endpoint_id)

    return ModelRouter(
        endpoints=endpoints,
        rules=rules,
        default_model=settings.gemini_pro_model,
    )


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

    # Model routing
    model_router = _build_model_router(settings)

    # Config
    loader = ConfigLoader(settings.config_dir)
    factory = AgentFactory(
        loader=loader,
        default_model=settings.gemini_pro_model,
        model_router=model_router,
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /mnt/c/Dev/GClaw && python -m pytest tests/test_main_routing.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run full test suite to check no regressions**

Run: `cd /mnt/c/Dev/GClaw && python -m pytest tests/ -v --tb=short`
Expected: All existing tests still pass

- [ ] **Step 6: Commit**

```bash
git add src/gclaw/main.py tests/test_main_routing.py
git commit -m "feat: wire ModelRouter into app startup with Gemma 4 and Nemotron support"
```

---

### Task 6: Admin API — Model Routing Status Endpoint

**Files:**
- Create: `src/gclaw/api/routing_routes.py`
- Modify: `src/gclaw/api/app.py`
- Create: `tests/test_routing_routes.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_routing_routes.py
"""Tests for model routing admin endpoints."""

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from gclaw.api.routing_routes import init_routing_router
from gclaw.models.model_config import ModelEndpoint, TaskProfile, RoutingRule
from gclaw.routing.router import ModelRouter


@pytest.fixture
def router():
    endpoints = {
        "gemini-pro": ModelEndpoint(
            name="gemini-pro",
            endpoint_id="gemini-2.5-pro",
            max_context_tokens=1_000_000,
        ),
        "gemma-4": ModelEndpoint(
            name="gemma-4",
            endpoint_id="projects/test/locations/us-central1/endpoints/111",
            max_context_tokens=256_000,
        ),
    }
    rules = [
        RoutingRule(task_profile=TaskProfile.ORCHESTRATION, model_name="gemini-pro"),
        RoutingRule(task_profile=TaskProfile.SUMMARIZATION, model_name="gemma-4"),
    ]
    return ModelRouter(endpoints=endpoints, rules=rules, default_model="gemini-2.5-flash")


@pytest.fixture
def client(router):
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(init_routing_router(router))
    return TestClient(app)


def test_get_routing_status(client):
    resp = client.get("/routing/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is True
    assert len(data["endpoints"]) == 2
    assert len(data["rules"]) == 2


def test_get_routing_resolve(client):
    resp = client.get("/routing/resolve/orchestration")
    assert resp.status_code == 200
    data = resp.json()
    assert data["profile"] == "orchestration"
    assert data["model_id"] == "gemini-2.5-pro"


def test_get_routing_resolve_agent(client):
    resp = client.get("/routing/resolve-agent/orchestrator")
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_name"] == "orchestrator"
    assert data["model_id"] == "gemini-2.5-pro"


def test_routing_disabled():
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(init_routing_router(None))
    client = TestClient(app)
    resp = client.get("/routing/status")
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/c/Dev/GClaw && python -m pytest tests/test_routing_routes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gclaw.api.routing_routes'`

- [ ] **Step 3: Write the routing routes**

```python
# src/gclaw/api/routing_routes.py
"""Admin endpoints for model routing status and resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter

from gclaw.models.model_config import TaskProfile

if TYPE_CHECKING:
    from gclaw.routing.router import ModelRouter


def init_routing_router(model_router: ModelRouter | None) -> APIRouter:
    router = APIRouter(prefix="/routing", tags=["routing"])

    @router.get("/status")
    def routing_status():
        if model_router is None:
            return {"enabled": False, "endpoints": [], "rules": []}

        return {
            "enabled": True,
            "endpoints": [
                {
                    "name": ep.name,
                    "endpoint_id": ep.endpoint_id,
                    "provider": ep.provider,
                    "max_context_tokens": ep.max_context_tokens,
                }
                for ep in model_router._endpoints.values()
            ],
            "rules": [
                {"profile": profile.value, "model": name}
                for profile, name in model_router._rules.items()
            ],
        }

    @router.get("/resolve/{profile}")
    def resolve_profile(profile: str):
        if model_router is None:
            return {"profile": profile, "model_id": None, "enabled": False}

        task_profile = TaskProfile(profile)
        model_id = model_router.resolve(task_profile)
        endpoint = model_router.get_endpoint(task_profile)
        return {
            "profile": profile,
            "model_id": model_id,
            "endpoint": {
                "name": endpoint.name,
                "provider": endpoint.provider,
                "max_context_tokens": endpoint.max_context_tokens,
            } if endpoint else None,
        }

    @router.get("/resolve-agent/{agent_name}")
    def resolve_agent(agent_name: str):
        if model_router is None:
            return {"agent_name": agent_name, "model_id": None, "enabled": False}

        model_id = model_router.resolve_for_agent(agent_name)
        return {
            "agent_name": agent_name,
            "model_id": model_id,
        }

    return router
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /mnt/c/Dev/GClaw && python -m pytest tests/test_routing_routes.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Wire routing router into app.py**

In `src/gclaw/api/app.py`, add the routing router import and initialization. Add to the `create_app` function signature: `model_router=None`. Inside the function, after other router initializations, add:

```python
from gclaw.api.routing_routes import init_routing_router
app.include_router(init_routing_router(model_router))
```

Also update `src/gclaw/main.py` to pass `model_router` to `create_app`:

In the `build_app()` function, change the `create_app` call to:

```python
return create_app(board_service=board_service, agent_runner=runner, model_router=model_router)
```

- [ ] **Step 6: Run full test suite**

Run: `cd /mnt/c/Dev/GClaw && python -m pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add src/gclaw/api/routing_routes.py src/gclaw/api/app.py src/gclaw/main.py tests/test_routing_routes.py
git commit -m "feat: add /routing admin endpoints for model status and resolution"
```

---

### Task 7: Context Compression — Three-Tier System

**Files:**
- Create: `src/gclaw/session/compaction.py`
- Create: `tests/test_session_compaction.py`

This implements the three-layer context compression pattern inspired by the Claude Code leak:
1. **MicroCompact** — trim old messages locally, zero API cost
2. **AutoCompact** — LLM-generated summary when approaching context limit
3. **FullCompact** — complete conversation reset with selective re-injection

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_session_compaction.py
"""Tests for three-tier context compaction."""

import pytest
from gclaw.session.compaction import CompactionStrategy, CompactionResult, ContextCompactor


def test_compaction_strategy_values():
    assert CompactionStrategy.MICRO == "micro"
    assert CompactionStrategy.AUTO == "auto"
    assert CompactionStrategy.FULL == "full"


def test_compaction_result():
    result = CompactionResult(
        strategy=CompactionStrategy.MICRO,
        messages_before=50,
        messages_after=20,
        summary=None,
    )
    assert result.tokens_saved == 0  # No token counting in micro


def test_context_compactor_select_micro():
    compactor = ContextCompactor(
        micro_threshold=30,
        auto_threshold=50,
        full_threshold=80,
    )
    strategy = compactor.select_strategy(message_count=35)
    assert strategy == CompactionStrategy.MICRO


def test_context_compactor_select_auto():
    compactor = ContextCompactor(
        micro_threshold=30,
        auto_threshold=50,
        full_threshold=80,
    )
    strategy = compactor.select_strategy(message_count=55)
    assert strategy == CompactionStrategy.AUTO


def test_context_compactor_select_full():
    compactor = ContextCompactor(
        micro_threshold=30,
        auto_threshold=50,
        full_threshold=80,
    )
    strategy = compactor.select_strategy(message_count=85)
    assert strategy == CompactionStrategy.FULL


def test_context_compactor_below_threshold():
    compactor = ContextCompactor(
        micro_threshold=30,
        auto_threshold=50,
        full_threshold=80,
    )
    strategy = compactor.select_strategy(message_count=10)
    assert strategy is None


def test_micro_compact():
    compactor = ContextCompactor(
        micro_threshold=30,
        auto_threshold=50,
        full_threshold=80,
    )
    messages = [f"msg-{i}" for i in range(40)]
    result = compactor.micro_compact(messages, keep_recent=20)
    assert result.strategy == CompactionStrategy.MICRO
    assert result.messages_after == 20
    assert result.kept_messages == messages[-20:]


def test_micro_compact_preserves_system():
    compactor = ContextCompactor(
        micro_threshold=30,
        auto_threshold=50,
        full_threshold=80,
    )
    messages = ["[system] init"] + [f"msg-{i}" for i in range(40)]
    result = compactor.micro_compact(messages, keep_recent=10, preserve_system=True)
    assert result.kept_messages[0] == "[system] init"
    assert len(result.kept_messages) == 11  # 1 system + 10 recent


def test_circuit_breaker_trips():
    compactor = ContextCompactor(
        micro_threshold=30,
        auto_threshold=50,
        full_threshold=80,
        max_consecutive_failures=3,
    )
    compactor.record_failure()
    compactor.record_failure()
    compactor.record_failure()
    assert compactor.circuit_open is True


def test_circuit_breaker_resets_on_success():
    compactor = ContextCompactor(
        micro_threshold=30,
        auto_threshold=50,
        full_threshold=80,
        max_consecutive_failures=3,
    )
    compactor.record_failure()
    compactor.record_failure()
    compactor.record_success()
    assert compactor.circuit_open is False
    assert compactor._consecutive_failures == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/c/Dev/GClaw && python -m pytest tests/test_session_compaction.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gclaw.session.compaction'`

- [ ] **Step 3: Write the compaction implementation**

```python
# src/gclaw/session/compaction.py
"""Three-tier context compaction inspired by Claude Code's compression system.

Tiers:
1. MicroCompact — drop old messages, keep recent. Zero API cost.
2. AutoCompact — LLM-generated summary when approaching limit.
3. FullCompact — complete reset with selective re-injection.

Includes a circuit breaker to prevent runaway compression attempts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class CompactionStrategy(str, Enum):
    MICRO = "micro"
    AUTO = "auto"
    FULL = "full"


@dataclass
class CompactionResult:
    strategy: CompactionStrategy
    messages_before: int
    messages_after: int
    summary: str | None = None
    kept_messages: list[str] = field(default_factory=list)
    tokens_saved: int = 0


class ContextCompactor:
    """Selects and executes context compaction strategies.

    Thresholds are in message count. For token-based thresholds,
    the caller should estimate tokens and convert to equivalent message counts.
    """

    def __init__(
        self,
        micro_threshold: int = 30,
        auto_threshold: int = 50,
        full_threshold: int = 80,
        max_consecutive_failures: int = 3,
    ) -> None:
        self._micro = micro_threshold
        self._auto = auto_threshold
        self._full = full_threshold
        self._max_failures = max_consecutive_failures
        self._consecutive_failures = 0

    @property
    def circuit_open(self) -> bool:
        return self._consecutive_failures >= self._max_failures

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        if self.circuit_open:
            logger.warning(
                "Compaction circuit breaker tripped after %d failures",
                self._consecutive_failures,
            )

    def record_success(self) -> None:
        self._consecutive_failures = 0

    def select_strategy(self, message_count: int) -> CompactionStrategy | None:
        """Select compaction strategy based on message count.

        Returns None if no compaction is needed.
        """
        if message_count >= self._full:
            return CompactionStrategy.FULL
        if message_count >= self._auto:
            return CompactionStrategy.AUTO
        if message_count >= self._micro:
            return CompactionStrategy.MICRO
        return None

    def micro_compact(
        self,
        messages: list[str],
        keep_recent: int = 20,
        preserve_system: bool = False,
    ) -> CompactionResult:
        """Drop old messages, keep only recent ones.

        If preserve_system is True, the first message is kept regardless
        (assumed to be a system/init message).
        """
        before = len(messages)

        if preserve_system and messages:
            system = [messages[0]]
            recent = messages[-keep_recent:]
            kept = system + recent
        else:
            kept = messages[-keep_recent:]

        return CompactionResult(
            strategy=CompactionStrategy.MICRO,
            messages_before=before,
            messages_after=len(kept),
            kept_messages=kept,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /mnt/c/Dev/GClaw && python -m pytest tests/test_session_compaction.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add src/gclaw/session/compaction.py tests/test_session_compaction.py
git commit -m "feat: add three-tier context compaction with circuit breaker"
```

---

### Task 8: Memory Consolidation — autoDream Pattern

**Files:**
- Create: `src/gclaw/memory/consolidation.py`
- Create: `tests/test_memory_consolidation.py`

Implements the four-phase idle-time memory consolidation pattern:
Orient -> Gather Signal -> Consolidate -> Prune/Index

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_memory_consolidation.py
"""Tests for memory consolidation (autoDream pattern)."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from gclaw.memory.consolidation import (
    ConsolidationPhase,
    ConsolidationResult,
    MemoryConsolidator,
)
from gclaw.models.memory import Memory


def test_consolidation_phase_values():
    assert ConsolidationPhase.ORIENT == "orient"
    assert ConsolidationPhase.GATHER == "gather"
    assert ConsolidationPhase.CONSOLIDATE == "consolidate"
    assert ConsolidationPhase.PRUNE == "prune"


def test_consolidation_result():
    result = ConsolidationResult(
        memories_scanned=100,
        memories_pruned=20,
        memories_merged=5,
        soul_updates=[],
    )
    assert result.memories_scanned == 100
    assert result.net_reduction == 20


@pytest.mark.asyncio
async def test_orient_phase():
    memory_service = AsyncMock()
    memory_service.recall.return_value = [
        Memory(fact="User prefers dark mode", topic="preferences", score=0.9),
        Memory(fact="User prefers dark mode in apps", topic="preferences", score=0.8),
    ]

    consolidator = MemoryConsolidator(
        memory_service=memory_service,
        max_memories=200,
    )
    candidates = await consolidator.orient(user_id="user1")
    assert len(candidates) == 2


@pytest.mark.asyncio
async def test_gather_finds_duplicates():
    consolidator = MemoryConsolidator(
        memory_service=AsyncMock(),
        max_memories=200,
    )
    memories = [
        Memory(fact="User prefers dark mode", topic="preferences", score=0.9),
        Memory(fact="User prefers dark mode in apps", topic="preferences", score=0.8),
        Memory(fact="User works at Acme Corp", topic="context", score=0.7),
    ]
    groups = consolidator.gather_signal(memories, similarity_threshold=0.7)
    # Two preference memories should group together
    assert len(groups) >= 1


@pytest.mark.asyncio
async def test_prune_respects_max():
    consolidator = MemoryConsolidator(
        memory_service=AsyncMock(),
        max_memories=2,
    )
    memories = [
        Memory(fact="fact1", topic="a", score=0.9),
        Memory(fact="fact2", topic="b", score=0.5),
        Memory(fact="fact3", topic="c", score=0.3),
    ]
    pruned = consolidator.prune(memories)
    assert len(pruned) == 2
    assert pruned[0].score >= pruned[1].score
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/c/Dev/GClaw && python -m pytest tests/test_memory_consolidation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gclaw.memory.consolidation'`

- [ ] **Step 3: Write the consolidation implementation**

```python
# src/gclaw/memory/consolidation.py
"""Memory consolidation — the autoDream pattern.

Runs during idle time to keep memory clean and within budget.
Four phases: Orient, Gather Signal, Consolidate, Prune/Index.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from gclaw.models.memory import Memory

if TYPE_CHECKING:
    from gclaw.memory.service import MemoryService

logger = logging.getLogger(__name__)


class ConsolidationPhase(str, Enum):
    ORIENT = "orient"
    GATHER = "gather"
    CONSOLIDATE = "consolidate"
    PRUNE = "prune"


@dataclass
class ConsolidationResult:
    memories_scanned: int = 0
    memories_pruned: int = 0
    memories_merged: int = 0
    soul_updates: list[str] = field(default_factory=list)

    @property
    def net_reduction(self) -> int:
        return self.memories_pruned


class MemoryConsolidator:
    """Four-phase memory consolidation for idle-time maintenance."""

    def __init__(
        self,
        memory_service: MemoryService,
        max_memories: int = 200,
    ) -> None:
        self._memory = memory_service
        self._max = max_memories

    async def orient(self, user_id: str) -> list[Memory]:
        """Phase 1: Scan recent memories to find consolidation candidates.

        Retrieves all user-scoped memories using a broad query.
        """
        return await self._memory.recall(
            user_id=user_id,
            query="all user preferences, habits, and context",
            top_k=self._max,
        )

    def gather_signal(
        self,
        memories: list[Memory],
        similarity_threshold: float = 0.7,
    ) -> list[list[Memory]]:
        """Phase 2: Group memories by topic for deduplication.

        Groups memories that share the same topic and have overlapping
        content. Uses simple topic-based grouping (not embedding similarity,
        which would require an additional API call).
        """
        by_topic: dict[str, list[Memory]] = {}
        for m in memories:
            topic = m.topic or "general"
            if topic not in by_topic:
                by_topic[topic] = []
            by_topic[topic].append(m)

        # Return groups with 2+ memories (candidates for merging)
        return [group for group in by_topic.values() if len(group) >= 2]

    def prune(self, memories: list[Memory]) -> list[Memory]:
        """Phase 4: Trim memory list to max budget, keeping highest-scored.

        Returns the top N memories by score.
        """
        sorted_memories = sorted(memories, key=lambda m: m.score, reverse=True)
        return sorted_memories[: self._max]

    async def run(self, user_id: str) -> ConsolidationResult:
        """Execute all four consolidation phases.

        Returns a ConsolidationResult summarizing what was done.
        """
        result = ConsolidationResult()

        # Phase 1: Orient
        memories = await self.orient(user_id)
        result.memories_scanned = len(memories)

        if not memories:
            return result

        # Phase 2: Gather Signal
        groups = self.gather_signal(memories)
        result.memories_merged = len(groups)

        # Phase 3: Consolidate (log groups for now — future: LLM merge)
        for group in groups:
            topic = group[0].topic or "general"
            logger.info(
                "Consolidation candidate: topic=%s, count=%d",
                topic,
                len(group),
            )

        # Phase 4: Prune
        pruned = self.prune(memories)
        result.memories_pruned = len(memories) - len(pruned)

        return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /mnt/c/Dev/GClaw && python -m pytest tests/test_memory_consolidation.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/gclaw/memory/consolidation.py tests/test_memory_consolidation.py
git commit -m "feat: add memory consolidation (autoDream pattern) for idle-time maintenance"
```

---

### Task 9: Tool Governance — Permission-Gated Tool Registry

**Files:**
- Create: `src/gclaw/tools/governance.py`
- Create: `tests/test_tool_governance.py`

Implements per-tool risk tiers and agent-level permission checks, inspired by Claude Code's 23-check security system and NeMo Guardrails' role-based access control.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_tool_governance.py
"""Tests for tool governance and permission gating."""

import pytest
from gclaw.tools.governance import ToolRisk, ToolGrant, ToolGovernor


def test_tool_risk_ordering():
    assert ToolRisk.READ_ONLY.value < ToolRisk.WRITE.value
    assert ToolRisk.WRITE.value < ToolRisk.SYSTEM.value


def test_tool_grant():
    grant = ToolGrant(
        tool_name="gmail_send",
        risk=ToolRisk.WRITE,
        allowed_agents=["workspace-mgr", "comms-mgr"],
    )
    assert grant.tool_name == "gmail_send"
    assert "workspace-mgr" in grant.allowed_agents


def test_governor_allows_granted_agent():
    grants = [
        ToolGrant(
            tool_name="gmail_send",
            risk=ToolRisk.WRITE,
            allowed_agents=["workspace-mgr"],
        ),
    ]
    gov = ToolGovernor(grants=grants)
    assert gov.is_allowed("gmail_send", "workspace-mgr") is True


def test_governor_blocks_ungated_agent():
    grants = [
        ToolGrant(
            tool_name="gmail_send",
            risk=ToolRisk.WRITE,
            allowed_agents=["workspace-mgr"],
        ),
    ]
    gov = ToolGovernor(grants=grants)
    assert gov.is_allowed("gmail_send", "research-mgr") is False


def test_governor_unknown_tool_denied():
    gov = ToolGovernor(grants=[])
    assert gov.is_allowed("unknown_tool", "orchestrator") is False


def test_governor_read_only_allowed_for_all():
    grants = [
        ToolGrant(
            tool_name="list_board_tasks",
            risk=ToolRisk.READ_ONLY,
            allowed_agents=["*"],
        ),
    ]
    gov = ToolGovernor(grants=grants)
    assert gov.is_allowed("list_board_tasks", "any-agent") is True


def test_governor_system_requires_approval():
    grants = [
        ToolGrant(
            tool_name="delete_user_data",
            risk=ToolRisk.SYSTEM,
            allowed_agents=["orchestrator"],
            requires_approval=True,
        ),
    ]
    gov = ToolGovernor(grants=grants)
    assert gov.requires_approval("delete_user_data") is True
    assert gov.requires_approval("unknown_tool") is False


def test_governor_get_tools_for_agent():
    grants = [
        ToolGrant(tool_name="gmail_send", risk=ToolRisk.WRITE, allowed_agents=["workspace-mgr"]),
        ToolGrant(tool_name="gmail_read", risk=ToolRisk.READ_ONLY, allowed_agents=["*"]),
        ToolGrant(tool_name="github_push", risk=ToolRisk.WRITE, allowed_agents=["dev-mgr"]),
    ]
    gov = ToolGovernor(grants=grants)
    tools = gov.get_allowed_tools("workspace-mgr")
    tool_names = [t.tool_name for t in tools]
    assert "gmail_send" in tool_names
    assert "gmail_read" in tool_names
    assert "github_push" not in tool_names


def test_audit_log():
    grants = [
        ToolGrant(tool_name="gmail_send", risk=ToolRisk.WRITE, allowed_agents=["workspace-mgr"]),
    ]
    gov = ToolGovernor(grants=grants)
    gov.check_and_log("gmail_send", "workspace-mgr")
    gov.check_and_log("gmail_send", "research-mgr")
    assert len(gov.audit_log) == 2
    assert gov.audit_log[0]["allowed"] is True
    assert gov.audit_log[1]["allowed"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/c/Dev/GClaw && python -m pytest tests/test_tool_governance.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gclaw.tools'`

- [ ] **Step 3: Create the tools package and governance module**

```bash
mkdir -p src/gclaw/tools
touch src/gclaw/tools/__init__.py
```

```python
# src/gclaw/tools/governance.py
"""Tool governance — permission-gated tool access with audit logging.

Each tool has a risk tier and a list of agents allowed to use it.
The ToolGovernor checks permissions and logs all access attempts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

logger = logging.getLogger(__name__)


class ToolRisk(IntEnum):
    """Risk tiers for tools. Higher value = more dangerous."""

    READ_ONLY = 1
    WRITE = 2
    SYSTEM = 3


@dataclass
class ToolGrant:
    """Permission grant for a tool."""

    tool_name: str
    risk: ToolRisk
    allowed_agents: list[str]
    requires_approval: bool = False


class ToolGovernor:
    """Enforces tool-level permissions and logs access attempts."""

    def __init__(self, grants: list[ToolGrant]) -> None:
        self._grants: dict[str, ToolGrant] = {g.tool_name: g for g in grants}
        self.audit_log: list[dict[str, Any]] = []

    def is_allowed(self, tool_name: str, agent_name: str) -> bool:
        grant = self._grants.get(tool_name)
        if grant is None:
            return False
        if "*" in grant.allowed_agents:
            return True
        return agent_name in grant.allowed_agents

    def requires_approval(self, tool_name: str) -> bool:
        grant = self._grants.get(tool_name)
        if grant is None:
            return False
        return grant.requires_approval

    def get_allowed_tools(self, agent_name: str) -> list[ToolGrant]:
        return [
            g
            for g in self._grants.values()
            if "*" in g.allowed_agents or agent_name in g.allowed_agents
        ]

    def check_and_log(
        self,
        tool_name: str,
        agent_name: str,
    ) -> bool:
        allowed = self.is_allowed(tool_name, agent_name)
        entry = {
            "tool": tool_name,
            "agent": agent_name,
            "allowed": allowed,
            "risk": self._grants[tool_name].risk.name if tool_name in self._grants else "UNKNOWN",
        }
        self.audit_log.append(entry)

        if not allowed:
            logger.warning(
                "Tool access DENIED: agent=%s tool=%s",
                agent_name,
                tool_name,
            )
        return allowed
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /mnt/c/Dev/GClaw && python -m pytest tests/test_tool_governance.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add src/gclaw/tools/__init__.py src/gclaw/tools/governance.py tests/test_tool_governance.py
git commit -m "feat: add tool governance with risk tiers, permission gating, and audit logging"
```

---

### Task 10: Vertex AI Deployment Configuration

**Files:**
- Create: `infra/vertex-models/deploy-gemma4.sh`
- Create: `infra/vertex-models/deploy-nemotron.sh`
- Create: `infra/vertex-models/README.md`

These are deployment scripts for provisioning model endpoints on Vertex AI.

- [ ] **Step 1: Create the infrastructure directory**

```bash
mkdir -p infra/vertex-models
```

- [ ] **Step 2: Write the Gemma 4 deployment script**

```bash
# infra/vertex-models/deploy-gemma4.sh
#!/usr/bin/env bash
# Deploy Gemma 4 31B to a Vertex AI endpoint in the your-project project.
#
# Prerequisites:
#   - gcloud CLI authenticated with sufficient permissions
#   - Vertex AI API enabled on the target project
#   - Sufficient GPU quota (L4 or A100 recommended for 31B)
#
# Usage:
#   ./deploy-gemma4.sh [PROJECT_ID] [REGION]

set -euo pipefail

PROJECT_ID="${1:-your-project}"
REGION="${2:-us-central1}"
MODEL_ID="google/gemma-4-31b-it"
ENDPOINT_NAME="gclaw-gemma4-31b"
MACHINE_TYPE="g2-standard-48"  # 4x L4 GPUs
ACCELERATOR_TYPE="NVIDIA_L4"
ACCELERATOR_COUNT=4

echo "==> Deploying Gemma 4 31B to Vertex AI"
echo "    Project: ${PROJECT_ID}"
echo "    Region:  ${REGION}"
echo "    Machine: ${MACHINE_TYPE} (${ACCELERATOR_COUNT}x ${ACCELERATOR_TYPE})"

# Create endpoint if it doesn't exist
ENDPOINT_ID=$(gcloud ai endpoints list \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --filter="displayName=${ENDPOINT_NAME}" \
    --format="value(name)" 2>/dev/null || true)

if [ -z "${ENDPOINT_ID}" ]; then
    echo "==> Creating endpoint: ${ENDPOINT_NAME}"
    gcloud ai endpoints create \
        --project="${PROJECT_ID}" \
        --region="${REGION}" \
        --display-name="${ENDPOINT_NAME}"

    ENDPOINT_ID=$(gcloud ai endpoints list \
        --project="${PROJECT_ID}" \
        --region="${REGION}" \
        --filter="displayName=${ENDPOINT_NAME}" \
        --format="value(name)")
fi

echo "==> Endpoint ID: ${ENDPOINT_ID}"

# Upload model from Model Garden
echo "==> Uploading model from Model Garden: ${MODEL_ID}"
gcloud ai models upload \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --display-name="gemma-4-31b-it" \
    --container-image-uri="us-docker.pkg.dev/vertex-ai/prediction/vllm-serve:latest" \
    --artifact-uri="gs://vertex-model-garden-public-us/${MODEL_ID}" \
    --container-args="--model=${MODEL_ID},--max-model-len=65536,--tensor-parallel-size=4"

MODEL_RESOURCE=$(gcloud ai models list \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --filter="displayName=gemma-4-31b-it" \
    --sort-by="~createTime" \
    --limit=1 \
    --format="value(name)")

# Deploy model to endpoint
echo "==> Deploying model to endpoint"
gcloud ai endpoints deploy-model "${ENDPOINT_ID}" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --model="${MODEL_RESOURCE}" \
    --display-name="gemma-4-31b-serving" \
    --machine-type="${MACHINE_TYPE}" \
    --accelerator-type="${ACCELERATOR_TYPE}" \
    --accelerator-count="${ACCELERATOR_COUNT}" \
    --min-replica-count=0 \
    --max-replica-count=1

echo "==> Done. Set this in your .env:"
echo "    GEMMA_ENDPOINT_ID=${ENDPOINT_ID}"
```

- [ ] **Step 3: Write the Nemotron deployment script**

```bash
# infra/vertex-models/deploy-nemotron.sh
#!/usr/bin/env bash
# Deploy Nemotron 3 Super via NIM container on GKE, or via Vertex AI Model Garden.
#
# Option A (default): Vertex AI Model Garden endpoint
# Option B: NIM container on GKE (requires NVIDIA AI Enterprise license)
#
# Prerequisites:
#   - gcloud CLI authenticated
#   - Vertex AI API enabled
#   - Sufficient GPU quota (A100 80GB recommended for 120B MoE)
#
# Usage:
#   ./deploy-nemotron.sh [PROJECT_ID] [REGION]

set -euo pipefail

PROJECT_ID="${1:-your-project}"
REGION="${2:-us-central1}"
ENDPOINT_NAME="gclaw-nemotron3-super"
MACHINE_TYPE="a2-ultragpu-1g"  # 1x A100 80GB (MoE only activates 12B)
ACCELERATOR_TYPE="NVIDIA_A100_80GB"
ACCELERATOR_COUNT=1

echo "==> Deploying Nemotron 3 Super to Vertex AI"
echo "    Project: ${PROJECT_ID}"
echo "    Region:  ${REGION}"
echo "    Machine: ${MACHINE_TYPE} (${ACCELERATOR_COUNT}x ${ACCELERATOR_TYPE})"

# Create endpoint if it doesn't exist
ENDPOINT_ID=$(gcloud ai endpoints list \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --filter="displayName=${ENDPOINT_NAME}" \
    --format="value(name)" 2>/dev/null || true)

if [ -z "${ENDPOINT_ID}" ]; then
    echo "==> Creating endpoint: ${ENDPOINT_NAME}"
    gcloud ai endpoints create \
        --project="${PROJECT_ID}" \
        --region="${REGION}" \
        --display-name="${ENDPOINT_NAME}"

    ENDPOINT_ID=$(gcloud ai endpoints list \
        --project="${PROJECT_ID}" \
        --region="${REGION}" \
        --filter="displayName=${ENDPOINT_NAME}" \
        --format="value(name)")
fi

echo "==> Endpoint ID: ${ENDPOINT_ID}"

# Deploy from Model Garden (Nemotron 3 Super is available in Vertex AI)
echo "==> Uploading Nemotron 3 Super from Model Garden"
gcloud ai models upload \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --display-name="nemotron-3-super-120b" \
    --container-image-uri="us-docker.pkg.dev/vertex-ai/prediction/vllm-serve:latest" \
    --artifact-uri="gs://vertex-model-garden-public-us/nvidia/nemotron-3-super-120b-instruct" \
    --container-args="--model=nvidia/nemotron-3-super-120b-instruct,--max-model-len=131072,--tensor-parallel-size=1"

MODEL_RESOURCE=$(gcloud ai models list \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --filter="displayName=nemotron-3-super-120b" \
    --sort-by="~createTime" \
    --limit=1 \
    --format="value(name)")

# Deploy model to endpoint
echo "==> Deploying model to endpoint"
gcloud ai endpoints deploy-model "${ENDPOINT_ID}" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --model="${MODEL_RESOURCE}" \
    --display-name="nemotron-3-super-serving" \
    --machine-type="${MACHINE_TYPE}" \
    --accelerator-type="${ACCELERATOR_TYPE}" \
    --accelerator-count="${ACCELERATOR_COUNT}" \
    --min-replica-count=0 \
    --max-replica-count=1

echo "==> Done. Set this in your .env:"
echo "    NEMOTRON_ENDPOINT_ID=${ENDPOINT_ID}"
echo "    NEMOTRON_PROVIDER=vertex"
```

- [ ] **Step 4: Write the README**

```markdown
# Vertex AI Model Deployments

Deployment scripts for GClaw's multi-model routing layer.

## Architecture

| Agent Tier | Model | Deployment | Why |
|---|---|---|---|
| Root Orchestrator | Gemini 3 Pro | Vertex AI (managed) | Frontier reasoning for intent classification |
| Managers | Gemma 4 31B | Vertex AI (self-hosted) | ADK-native, cost-efficient, 256K context |
| Specialists | Nemotron 3 Super | Vertex AI (self-hosted) | 5x throughput, 1M context, RL-trained tool calling |

## Prerequisites

1. `gcloud` CLI authenticated with `roles/aiplatform.admin`
2. Vertex AI API enabled on `your-project` project
3. GPU quota in `us-central1`:
   - Gemma 4: 4x NVIDIA L4 (g2-standard-48)
   - Nemotron 3: 1x A100 80GB (a2-ultragpu-1g)

## Deployment

```bash
# Deploy Gemma 4 31B
chmod +x deploy-gemma4.sh
./deploy-gemma4.sh your-project us-central1

# Deploy Nemotron 3 Super
chmod +x deploy-nemotron.sh
./deploy-nemotron.sh your-project us-central1
```

## Environment Variables

After deployment, add to your `.env`:

```
MODEL_ROUTING_ENABLED=true
GEMMA_ENDPOINT_ID=projects/your-project/locations/us-central1/endpoints/<id>
NEMOTRON_ENDPOINT_ID=projects/your-project/locations/us-central1/endpoints/<id>
NEMOTRON_PROVIDER=vertex
```

## Cost Notes

- Both endpoints deploy with `min-replica-count=0` (scale to zero when idle)
- Gemma 4 31B: ~$4.50/hr when active (4x L4)
- Nemotron 3 Super: ~$5.50/hr when active (1x A100 80GB) — only 12B params active per token
- Gemini 3 Pro: pay-per-token via Vertex AI API (no endpoint cost)

## Scaling

For production, increase `max-replica-count` and consider dedicated reservations.
The Nemotron MoE architecture means a single A100 handles the 120B model since only 12B params activate per token.
```

- [ ] **Step 5: Commit**

```bash
git add infra/vertex-models/
git commit -m "feat: add Vertex AI deployment scripts for Gemma 4 and Nemotron 3 Super"
```

---

### Task 11: Integration — Consolidation Cron Job

**Files:**
- Modify: `src/gclaw/heartbeat/service.py`

Wire the memory consolidation into the heartbeat loop so it runs during idle periods.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_heartbeat_consolidation.py
"""Tests for memory consolidation triggered via heartbeat."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from gclaw.heartbeat.service import HeartbeatService


@pytest.mark.asyncio
async def test_heartbeat_runs_consolidation_when_idle():
    gatherer = MagicMock()
    gatherer.gather.return_value = {
        "board_summary": {
            "total_tasks": 0,
            "queued": 0,
            "in_progress": 0,
            "failed": 0,
            "needs_approval": 0,
        },
    }
    gatherer.gather_as_message.return_value = "No pending tasks."

    runner = AsyncMock()
    runner.run.return_value = MagicMock(
        text="All clear.",
        tool_calls=[],
    )

    consolidator = AsyncMock()
    consolidator.run.return_value = MagicMock(
        memories_scanned=50,
        memories_pruned=5,
        memories_merged=2,
    )

    log_repo = MagicMock()

    service = HeartbeatService(
        context_gatherer=gatherer,
        agent_runner=runner,
        log_repo=log_repo,
        user_id="user1",
        consolidator=consolidator,
    )

    result = await service.run()
    consolidator.run.assert_called_once_with(user_id="user1")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /mnt/c/Dev/GClaw && python -m pytest tests/test_heartbeat_consolidation.py -v`
Expected: FAIL with `TypeError: HeartbeatService.__init__() got an unexpected keyword argument 'consolidator'`

- [ ] **Step 3: Update HeartbeatService to accept and run consolidator**

In `src/gclaw/heartbeat/service.py`, update the `__init__` method to accept an optional `consolidator` parameter, and add a consolidation call at the end of `run()`:

Add to the imports at the top:

```python
if TYPE_CHECKING:
    from gclaw.memory.consolidation import MemoryConsolidator
```

(Add `from __future__ import annotations` and `from typing import TYPE_CHECKING` if not already present.)

Update `__init__`:

```python
    def __init__(
        self,
        context_gatherer: HeartbeatContextGatherer,
        agent_runner: AgentRunner,
        log_repo: HeartbeatLogRepo,
        user_id: str,
        session_id: str = "heartbeat",
        consolidator: MemoryConsolidator | None = None,
    ) -> None:
        self._gatherer = context_gatherer
        self._runner = agent_runner
        self._log_repo = log_repo
        self._user_id = user_id
        self._session_id = session_id
        self._consolidator = consolidator
```

Add at the end of the `run()` method, before the `return` statement:

```python
        # Run memory consolidation if available and board is idle
        if self._consolidator is not None and context["board_summary"]["in_progress"] == 0:
            try:
                consolidation = await self._consolidator.run(user_id=self._user_id)
                logger.info(
                    "Memory consolidation: scanned=%d pruned=%d merged=%d",
                    consolidation.memories_scanned,
                    consolidation.memories_pruned,
                    consolidation.memories_merged,
                )
            except Exception:
                logger.warning("Memory consolidation failed", exc_info=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /mnt/c/Dev/GClaw && python -m pytest tests/test_heartbeat_consolidation.py tests/test_heartbeat_service.py -v`
Expected: PASS (all heartbeat tests, including the new consolidation test)

- [ ] **Step 5: Commit**

```bash
git add src/gclaw/heartbeat/service.py tests/test_heartbeat_consolidation.py
git commit -m "feat: run memory consolidation during idle heartbeat cycles"
```

---

### Task 12: Environment Template and Documentation

**Files:**
- Modify: `.env.example` (create if doesn't exist)

- [ ] **Step 1: Check if .env.example exists**

```bash
ls -la /mnt/c/Dev/GClaw/.env.example 2>/dev/null || echo "does not exist"
```

- [ ] **Step 2: Create or update .env.example with model routing vars**

Add the following block to `.env.example` (create the file if it doesn't exist):

```bash
# === Model Routing (optional) ===
# Enable multi-model routing (Gemini + Gemma 4 + Nemotron)
MODEL_ROUTING_ENABLED=false

# Gemma 4 31B endpoint on Vertex AI
# Deploy with: ./infra/vertex-models/deploy-gemma4.sh
GEMMA_ENDPOINT_ID=

# Nemotron 3 Super endpoint on Vertex AI
# Deploy with: ./infra/vertex-models/deploy-nemotron.sh
NEMOTRON_ENDPOINT_ID=
NEMOTRON_PROVIDER=vertex
```

- [ ] **Step 3: Commit**

```bash
git add .env.example
git commit -m "docs: add model routing env vars to .env.example"
```

---

### Task 13: Full Integration Test

**Files:**
- Create: `tests/test_integration_routing.py`

End-to-end test that verifies the full routing pipeline from settings through factory to agent creation.

- [ ] **Step 1: Write the integration test**

```python
# tests/test_integration_routing.py
"""Integration test: model routing from settings to agent creation."""

import os
import pytest
from gclaw.settings import Settings
from gclaw.config.loader import ConfigLoader
from gclaw.agents.factory import AgentFactory
from gclaw.models.model_config import ModelEndpoint, TaskProfile, RoutingRule
from gclaw.routing.router import ModelRouter


@pytest.fixture
def config_dir(tmp_path):
    soul_dir = tmp_path / "soul"
    soul_dir.mkdir()
    (soul_dir / "base.md").write_text("You are helpful.\n")
    (soul_dir / "workspace.md").write_text("Professional tone.\n")
    (soul_dir / "dev.md").write_text("Technical and precise.\n")

    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "orchestrator.md").write_text("Route to managers.\n")
    (agents_dir / "workspace-mgr.md").write_text("Manage workspace.\n")
    (agents_dir / "dev-mgr.md").write_text("Manage dev tasks.\n")
    return tmp_path


@pytest.fixture
def full_router():
    endpoints = {
        "gemini-pro": ModelEndpoint(
            name="gemini-pro",
            endpoint_id="gemini-2.5-pro",
            max_context_tokens=1_000_000,
        ),
        "gemma-4": ModelEndpoint(
            name="gemma-4",
            endpoint_id="projects/your-project/locations/us-central1/endpoints/111",
            max_context_tokens=256_000,
        ),
        "nemotron-3-super": ModelEndpoint(
            name="nemotron-3-super",
            endpoint_id="projects/your-project/locations/us-central1/endpoints/222",
            max_context_tokens=1_000_000,
            provider="nim",
        ),
    }
    rules = [
        RoutingRule(task_profile=TaskProfile.ORCHESTRATION, model_name="gemini-pro"),
        RoutingRule(task_profile=TaskProfile.PERSONALITY, model_name="gemini-pro"),
        RoutingRule(task_profile=TaskProfile.TOOL_EXECUTION, model_name="nemotron-3-super"),
        RoutingRule(task_profile=TaskProfile.CODE_GENERATION, model_name="nemotron-3-super"),
        RoutingRule(task_profile=TaskProfile.SUMMARIZATION, model_name="gemma-4"),
        RoutingRule(task_profile=TaskProfile.BACKGROUND, model_name="gemma-4"),
    ]
    return ModelRouter(endpoints=endpoints, rules=rules, default_model="gemini-2.5-flash")


def test_orchestrator_gets_gemini(config_dir, full_router):
    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(loader=loader, default_model="gemini-2.5-flash", model_router=full_router)
    agent = factory.build(agent_name="orchestrator")
    assert agent.model == "gemini-2.5-pro"


def test_workspace_mgr_gets_gemma(config_dir, full_router):
    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(loader=loader, default_model="gemini-2.5-flash", model_router=full_router)
    agent = factory.build(agent_name="workspace-mgr", soul_overlay="workspace")
    assert "111" in agent.model  # Gemma 4 endpoint


def test_dev_mgr_gets_nemotron(config_dir, full_router):
    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(loader=loader, default_model="gemini-2.5-flash", model_router=full_router)
    agent = factory.build(agent_name="dev-mgr", soul_overlay="dev")
    assert "222" in agent.model  # Nemotron endpoint


def test_unknown_agent_gets_default(config_dir, full_router):
    # Create a generic agent definition
    agents_dir = config_dir / "agents"
    (agents_dir / "generic.md").write_text("A generic agent.\n")

    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(loader=loader, default_model="gemini-2.5-flash", model_router=full_router)
    agent = factory.build(agent_name="generic")
    assert agent.model == "gemini-2.5-flash"


def test_explicit_model_overrides_routing(config_dir, full_router):
    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(loader=loader, default_model="gemini-2.5-flash", model_router=full_router)
    agent = factory.build(agent_name="orchestrator", model="custom-override")
    assert agent.model == "custom-override"


def test_routing_disabled_all_use_default(config_dir):
    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(loader=loader, default_model="gemini-2.5-flash")
    orchestrator = factory.build(agent_name="orchestrator")
    workspace = factory.build(agent_name="workspace-mgr", soul_overlay="workspace")
    assert orchestrator.model == "gemini-2.5-flash"
    assert workspace.model == "gemini-2.5-flash"
```

- [ ] **Step 2: Run integration tests**

Run: `cd /mnt/c/Dev/GClaw && python -m pytest tests/test_integration_routing.py -v`
Expected: PASS (6 tests)

- [ ] **Step 3: Run full test suite**

Run: `cd /mnt/c/Dev/GClaw && python -m pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration_routing.py
git commit -m "test: add integration tests for full model routing pipeline"
```

---

## Summary

| Task | What it builds | New files | Tests |
|------|---------------|-----------|-------|
| 1 | Model config data models | `models/model_config.py` | 4 |
| 2 | Settings env vars | `settings.py` (modify) | 2 |
| 3 | ModelRouter core logic | `routing/router.py` | 10 |
| 4 | AgentFactory integration | `factory.py` (modify) | 3 |
| 5 | App startup wiring | `main.py` (modify) | 2 |
| 6 | Admin API endpoints | `api/routing_routes.py` | 4 |
| 7 | Context compression | `session/compaction.py` | 10 |
| 8 | Memory consolidation | `memory/consolidation.py` | 5 |
| 9 | Tool governance | `tools/governance.py` | 9 |
| 10 | Vertex AI deploy scripts | `infra/vertex-models/` | 0 |
| 11 | Heartbeat consolidation | `heartbeat/service.py` (modify) | 1 |
| 12 | Env template | `.env.example` | 0 |
| 13 | Integration tests | `test_integration_routing.py` | 6 |

**Total: 13 tasks, ~56 tests, 7 new files, 5 modified files, 3 infra scripts**
