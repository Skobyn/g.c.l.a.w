# Orchestration Refactor Implementation Plan

> **STATUS: shipped 2026-04-10 → 2026-04-11** — tool stubs (`tools/gws,gh,workspace,dev,comms,research,home`), workflows (`morning_brief`, `commit_message`, `validators`), AgentTool-based orchestrator rewrite, LiteLlm unification, manager agent/soul configs all landed in commits `3d3e989..6be3a2b` via PR #1 `1edcb61`. Archived 2026-04-11.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor GClaw's orchestration layer to use ADK-native multi-agent patterns (AgentTool, ParallelAgent, SequentialAgent, Reviewer/Validate) and unify all model providers under `LiteLlm`, retiring the bespoke `RemoteRunner`.

**Architecture:** The orchestrator becomes a pure router that wraps managers and composed workflows as `AgentTool` instances. Managers are thin routers bound to real subprocess-backed domain tools (`gws` for Google Workspace, `gh` for GitHub, stubs for Home/Research). Non-Gemini providers route through ADK's `LiteLlm` wrapper so every agent shares one execution path. Two composed workflows demonstrate the patterns: a morning brief (`ParallelAgent` + `SequentialAgent`) and a commit-message generator (`SequentialAgent` + Reviewer + Validate).

**Tech Stack:** Python 3.12, google-adk (with `[extensions]` for LiteLlm), FastAPI, Pydantic, pytest, pytest-asyncio, subprocess-backed `gws` and `gh` CLIs.

**Spec:** `docs/superpowers/specs/2026-04-10-orchestration-refactor-design.md`

---

## File Structure

### Created

| File | Responsibility |
|---|---|
| `src/gclaw/tools/gws.py` | `run_gws(*args)` — async subprocess wrapper around `gws` CLI with JSON stdout parsing |
| `src/gclaw/tools/gh.py` | `run_gh(*args)` — async subprocess wrapper around `gh` CLI with JSON stdout parsing |
| `src/gclaw/tools/workspace_tools.py` | Thin tool fns: `list_unread_email`, `send_email`, `list_calendar_events_today`, `create_calendar_event`, `list_drive_files`, `read_drive_doc` |
| `src/gclaw/tools/dev_tools.py` | Thin tool fns: `list_open_prs`, `get_pr_diff`, `list_failing_workflows`, `create_issue`, `get_current_diff`, `read_local_file` |
| `src/gclaw/tools/comms_tools.py` | Thin tool fns: `list_chat_spaces`, `post_chat_message` |
| `src/gclaw/tools/research_tools.py` | Thin tool fns: `web_search` (stub), `fetch_url` (httpx) |
| `src/gclaw/tools/home_tools.py` | Stubs: `list_devices`, `set_device_state` |
| `src/gclaw/agents/workflows/__init__.py` | Package marker |
| `src/gclaw/agents/workflows/morning_brief.py` | `build_morning_brief(...)` returning a `SequentialAgent` |
| `src/gclaw/agents/workflows/commit_message.py` | `build_commit_message_workflow(...)` returning a `SequentialAgent` |
| `src/gclaw/agents/workflows/validators.py` | `ValidateCommitMsg(BaseAgent)` — final gate for the commit workflow |
| `agents/home-mgr.md` | Home manager agent definition |
| `agents/comms-mgr.md` | Comms manager agent definition |
| `agents/research-mgr.md` | Research manager agent definition |
| `soul/home.md` | Home manager personality overlay |
| `soul/comms.md` | Comms manager personality overlay |
| `soul/research.md` | Research manager personality overlay |
| `tests/test_tools_gws.py` | Unit tests for `run_gws` |
| `tests/test_tools_gh.py` | Unit tests for `run_gh` |
| `tests/test_workspace_tools.py` | Unit tests for workspace tool fns |
| `tests/test_dev_tools.py` | Unit tests for dev tool fns |
| `tests/test_comms_tools.py` | Unit tests for comms tool fns |
| `tests/test_research_tools.py` | Unit tests for research tool fns |
| `tests/test_home_tools.py` | Unit tests for home stub fns |
| `tests/test_router_adk_model.py` | Unit tests for `build_adk_model_*` helpers |
| `tests/test_factory_output_key.py` | Unit tests for factory `output_key` and LiteLlm resolution |
| `tests/test_workflows_validators.py` | Unit tests for `ValidateCommitMsg` pass/fail paths |
| `tests/test_workflows_morning_brief.py` | Unit tests for morning brief structure |
| `tests/test_workflows_commit_message.py` | Unit tests for commit message workflow structure |
| `tests/test_orchestrator_agenttool.py` | Integration test: orchestrator with AgentTool-wrapped managers |
| `tests/test_integration_litellm_providers.py` | Integration test: non-Gemini providers through LiteLlm |

### Modified

| File | Change |
|---|---|
| `pyproject.toml` | Add `google-adk[extensions]` dep |
| `Dockerfile` | Install `gws` and `gh` binaries |
| `.env.example` | Add `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` |
| `src/gclaw/settings.py` | Add `google_workspace_credentials_file` setting |
| `src/gclaw/routing/router.py` | Add `build_adk_model_for_profile`, `build_adk_model_for_agent` |
| `src/gclaw/agents/factory.py` | Add `output_key` param; route through `build_adk_model_for_agent` |
| `src/gclaw/agents/orchestrator.py` | Rewrite to use AgentTool for all delegation |
| `src/gclaw/dispatch/runner.py` | Remove `_run_remote` and `remote_runner` param |
| `src/gclaw/main.py` | Pass `router` + `default_model` to `build_orchestrator`; drop api_base/api_key_env wiring |
| `src/gclaw/models/model_config.py` | Remove `api_base`, `api_key_env`, `is_remote` from `ModelEndpoint` |
| `tests/test_dispatcher.py` | Remove `remote_runner` tests; add manager-target test |
| `tests/test_model_config.py` | Remove `api_base`/`is_remote` tests |

### Deleted

| File | Reason |
|---|---|
| `src/gclaw/dispatch/remote_runner.py` | Replaced by LiteLlm |
| `tests/test_remote_runner.py` | Module deleted |
| `tests/test_integration_providers.py` | Replaced by `test_integration_litellm_providers.py` |

---

### Task 1: Add `google-adk[extensions]` dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Update dependencies list**

Edit `pyproject.toml`. In the `[project]` `dependencies = [...]` list, change `"google-adk>=1.0.0"` to `"google-adk[extensions]>=1.0.0"`. Leave all other dependencies unchanged.

- [ ] **Step 2: Reinstall the package**

Run: `cd /mnt/c/Dev/GClaw && pip install -e ".[dev]"`
Expected: installation completes without errors. `litellm` is pulled in as a transitive dep.

- [ ] **Step 3: Verify LiteLlm is importable**

Run: `python3 -c "from google.adk.models.lite_llm import LiteLlm; print('ok')"`
Expected: prints `ok`. (Previously raised `ImportError: LiteLLM support requires: pip install google-adk[extensions]`.)

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "build: enable google-adk[extensions] for LiteLlm support"
```

---

### Task 2: Router — `build_adk_model_for_profile` and `build_adk_model_for_agent`

**Files:**
- Modify: `src/gclaw/routing/router.py`
- Create: `tests/test_router_adk_model.py`

This adds two helper methods that return ADK-ready model references: either a bare string (Gemini/Vertex) or a `LiteLlm` instance (non-Gemini). The factory will call these in Task 3.

- [ ] **Step 1: Write the failing test**

Create `tests/test_router_adk_model.py`:

```python
"""Tests for ModelRouter's ADK-ready model builders."""

from unittest.mock import patch

import pytest

from gclaw.models.model_config import ModelEndpoint, RoutingRule, TaskProfile
from gclaw.routing.router import ModelRouter


@pytest.fixture
def router():
    endpoints = {
        "gemini-flash": ModelEndpoint(
            name="gemini-flash",
            endpoint_id="gemini-2.5-flash",
            provider="gemini",
        ),
        "gemma-4": ModelEndpoint(
            name="gemma-4",
            endpoint_id="gemma-4-26b-it",
            provider="gemini",
        ),
        "nemotron-3-super": ModelEndpoint(
            name="nemotron-3-super",
            endpoint_id="nvidia/nemotron-3-super-120b-a12b:free",
            provider="openrouter",
        ),
    }
    rules = [
        RoutingRule(task_profile=TaskProfile.ORCHESTRATION, model_name="gemini-flash"),
        RoutingRule(task_profile=TaskProfile.SUMMARIZATION, model_name="gemma-4"),
        RoutingRule(task_profile=TaskProfile.CODE_GENERATION, model_name="nemotron-3-super"),
    ]
    return ModelRouter(endpoints=endpoints, rules=rules, default_model="gemini-2.5-flash")


def test_build_adk_model_for_profile_gemini_returns_string(router):
    result = router.build_adk_model_for_profile(TaskProfile.ORCHESTRATION)
    assert result == "gemini-2.5-flash"


def test_build_adk_model_for_profile_gemma_returns_string(router):
    result = router.build_adk_model_for_profile(TaskProfile.SUMMARIZATION)
    assert result == "gemma-4-26b-it"


def test_build_adk_model_for_profile_openrouter_returns_litellm(router):
    from google.adk.models.lite_llm import LiteLlm

    result = router.build_adk_model_for_profile(TaskProfile.CODE_GENERATION)
    assert isinstance(result, LiteLlm)
    # LiteLlm normalizes provider prefix on the model string.
    assert "nemotron" in result.model.lower()
    assert result.model.startswith("openrouter/")


def test_build_adk_model_for_profile_unknown_returns_default(router):
    result = router.build_adk_model_for_profile(TaskProfile.PERSONALITY)
    assert result == "gemini-2.5-flash"


def test_build_adk_model_for_agent_orchestrator(router):
    result = router.build_adk_model_for_agent("orchestrator")
    assert result == "gemini-2.5-flash"


def test_build_adk_model_for_agent_dev_mgr_returns_litellm(router):
    from google.adk.models.lite_llm import LiteLlm

    result = router.build_adk_model_for_agent("dev-mgr")
    assert isinstance(result, LiteLlm)


def test_build_adk_model_for_agent_unknown_returns_default(router):
    result = router.build_adk_model_for_agent("nonexistent-mgr")
    assert result == "gemini-2.5-flash"


def test_build_adk_model_for_agent_suffix_match(router):
    # Any agent with "code" in its name maps to CODE_GENERATION per SPECIALIST_SUFFIX_MAP.
    result = router.build_adk_model_for_agent("some-code-specialist")
    from google.adk.models.lite_llm import LiteLlm

    assert isinstance(result, LiteLlm)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/test_router_adk_model.py -v`
Expected: FAIL — `ModelRouter` has no attribute `build_adk_model_for_profile` / `build_adk_model_for_agent`.

- [ ] **Step 3: Update `src/gclaw/routing/router.py`**

Replace the file with:

```python
"""Model router — resolves task profiles to Vertex AI model endpoints.

Returns ADK-ready model references: a string (Gemini/Vertex) or a LiteLlm
instance (OpenRouter and other OpenAI-compatible providers) so ADK's native
Runner can execute agents uniformly regardless of provider.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Union

from gclaw.models.model_config import ModelEndpoint, RoutingRule, TaskProfile

if TYPE_CHECKING:
    from google.adk.models.lite_llm import LiteLlm

logger = logging.getLogger(__name__)

AGENT_PROFILE_MAP: dict[str, TaskProfile] = {
    "orchestrator": TaskProfile.ORCHESTRATION,
    "workspace-mgr": TaskProfile.SUMMARIZATION,
    "dev-mgr": TaskProfile.CODE_GENERATION,
    "home-mgr": TaskProfile.SUMMARIZATION,
    "comms-mgr": TaskProfile.PERSONALITY,
    "research-mgr": TaskProfile.SUMMARIZATION,
}

SPECIALIST_SUFFIX_MAP: dict[str, TaskProfile] = {
    "code": TaskProfile.CODE_GENERATION,
    "search": TaskProfile.TOOL_EXECUTION,
    "draft": TaskProfile.PERSONALITY,
    "summarize": TaskProfile.SUMMARIZATION,
    "audit": TaskProfile.TOOL_EXECUTION,
}

AdkModel = Union[str, "LiteLlm"]


def _endpoint_to_adk_model(
    endpoint: ModelEndpoint | None, default: str
) -> AdkModel:
    """Convert a ModelEndpoint to an ADK-ready model reference."""
    if endpoint is None:
        return default

    if endpoint.provider in ("gemini", "vertex"):
        return endpoint.endpoint_id

    from google.adk.models.lite_llm import LiteLlm

    prefixed = endpoint.endpoint_id
    if endpoint.provider == "openrouter" and not prefixed.startswith("openrouter/"):
        prefixed = f"openrouter/{prefixed}"

    return LiteLlm(model=prefixed)


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
        """Resolve a task profile to a bare model ID string (legacy)."""
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
        """Resolve an agent name to a bare model ID string (legacy)."""
        profile = AGENT_PROFILE_MAP.get(agent_name)
        if profile is not None:
            return self.resolve(profile)

        for suffix, prof in SPECIALIST_SUFFIX_MAP.items():
            if suffix in agent_name:
                return self.resolve(prof)

        return self._default

    def get_endpoint(self, profile: TaskProfile) -> ModelEndpoint | None:
        model_name = self._rules.get(profile)
        if model_name is None:
            return None
        return self._endpoints.get(model_name)

    def build_adk_model_for_profile(self, profile: TaskProfile) -> AdkModel:
        """Return an ADK-ready model for a task profile.

        Gemini/Vertex providers return a bare string model ID.
        Other providers return a LiteLlm instance ADK's native Runner can execute.
        """
        endpoint = self.get_endpoint(profile)
        return _endpoint_to_adk_model(endpoint, self._default)

    def build_adk_model_for_agent(self, agent_name: str) -> AdkModel:
        """Return an ADK-ready model for a named agent.

        Uses AGENT_PROFILE_MAP, falling back to SPECIALIST_SUFFIX_MAP matching.
        """
        profile = AGENT_PROFILE_MAP.get(agent_name)
        if profile is None:
            for suffix, prof in SPECIALIST_SUFFIX_MAP.items():
                if suffix in agent_name:
                    profile = prof
                    break
        if profile is None:
            return self._default
        return self.build_adk_model_for_profile(profile)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/test_router_adk_model.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Run the existing router tests to check for regressions**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/test_model_router.py -v`
Expected: PASS (no regressions).

- [ ] **Step 6: Commit**

```bash
git add src/gclaw/routing/router.py tests/test_router_adk_model.py
git commit -m "feat(router): add build_adk_model_for_profile and build_adk_model_for_agent"
```

---

### Task 3: Factory — accept `output_key` and resolve ADK models

**Files:**
- Modify: `src/gclaw/agents/factory.py`
- Create: `tests/test_factory_output_key.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_factory_output_key.py`:

```python
"""Tests for AgentFactory output_key support and ADK model resolution."""

import os
from unittest.mock import MagicMock

import pytest

from gclaw.agents.factory import AgentFactory
from gclaw.config.loader import ConfigLoader
from gclaw.models.model_config import ModelEndpoint, RoutingRule, TaskProfile
from gclaw.routing.router import ModelRouter


@pytest.fixture
def config_dir(tmp_path):
    soul_dir = tmp_path / "soul"
    soul_dir.mkdir()
    (soul_dir / "base.md").write_text("Base personality.\n")
    (soul_dir / "dev.md").write_text("Dev overlay.\n")
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "dev-mgr.md").write_text("Dev manager role.\n")
    (agents_dir / "orchestrator.md").write_text("Orchestrator role.\n")
    return tmp_path


@pytest.fixture
def router():
    endpoints = {
        "gemini-flash": ModelEndpoint(
            name="gemini-flash", endpoint_id="gemini-2.5-flash", provider="gemini",
        ),
        "nemotron-3-super": ModelEndpoint(
            name="nemotron-3-super",
            endpoint_id="nvidia/nemotron-3-super-120b-a12b:free",
            provider="openrouter",
        ),
    }
    rules = [
        RoutingRule(task_profile=TaskProfile.ORCHESTRATION, model_name="gemini-flash"),
        RoutingRule(task_profile=TaskProfile.CODE_GENERATION, model_name="nemotron-3-super"),
    ]
    return ModelRouter(endpoints=endpoints, rules=rules, default_model="gemini-2.5-flash")


def test_factory_accepts_output_key(config_dir, router):
    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(
        loader=loader,
        default_model="gemini-2.5-flash",
        model_router=router,
    )
    agent = factory.build(agent_name="orchestrator", output_key="orchestrator_result")
    assert agent.output_key == "orchestrator_result"


def test_factory_orchestrator_gets_string_model(config_dir, router):
    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(
        loader=loader,
        default_model="gemini-2.5-flash",
        model_router=router,
    )
    agent = factory.build(agent_name="orchestrator")
    # Gemini: bare string model ID
    assert agent.model == "gemini-2.5-flash"


def test_factory_dev_mgr_gets_litellm_instance(config_dir, router):
    from google.adk.models.lite_llm import LiteLlm

    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(
        loader=loader,
        default_model="gemini-2.5-flash",
        model_router=router,
    )
    agent = factory.build(agent_name="dev-mgr", soul_overlay="dev")
    # Non-Gemini: LiteLlm instance
    assert isinstance(agent.model, LiteLlm)


def test_factory_explicit_model_overrides_router(config_dir, router):
    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(
        loader=loader,
        default_model="gemini-2.5-flash",
        model_router=router,
    )
    agent = factory.build(agent_name="dev-mgr", soul_overlay="dev", model="custom-model")
    assert agent.model == "custom-model"


def test_factory_no_router_uses_default(config_dir):
    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(
        loader=loader,
        default_model="gemini-2.5-flash",
        model_router=None,
    )
    agent = factory.build(agent_name="orchestrator")
    assert agent.model == "gemini-2.5-flash"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/test_factory_output_key.py -v`
Expected: FAIL — `factory.build()` doesn't accept `output_key`, and currently calls `resolve_for_agent` which returns a string, not a LiteLlm instance.

- [ ] **Step 3: Replace `src/gclaw/agents/factory.py`**

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
        model_router: "ModelRouter | None" = None,
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
        model: Any | None = None,
        description: str | None = None,
        output_key: str | None = None,
    ) -> LlmAgent:
        instruction = self._loader.build_system_prompt(
            agent_name=agent_name,
            soul_base="base",
            soul_overlay=soul_overlay,
            memories=memories,
        )

        # Model resolution: explicit > router (as ADK-ready object) > default
        adk_model: Any
        if model is not None:
            adk_model = model
        elif self._router is not None:
            adk_model = self._router.build_adk_model_for_agent(agent_name)
        else:
            adk_model = self._default_model

        safe_name = agent_name.replace("-", "_")
        return LlmAgent(
            name=safe_name,
            model=adk_model,
            instruction=instruction,
            description=description or f"GClaw agent: {agent_name}",
            tools=tools or [],
            sub_agents=sub_agents or [],
            output_key=output_key,
        )
```

- [ ] **Step 4: Run the new test to verify it passes**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/test_factory_output_key.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Run the existing factory tests for regressions**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/ -k "factory" -v`
Expected: all factory-related tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/gclaw/agents/factory.py tests/test_factory_output_key.py
git commit -m "feat(factory): accept output_key and resolve to ADK-ready models"
```

---

### Task 4: `tools/gws.py` — subprocess helper for Google Workspace CLI

**Files:**
- Create: `src/gclaw/tools/gws.py`
- Create: `tests/test_tools_gws.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_tools_gws.py`:

```python
"""Tests for the gws subprocess helper."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gclaw.tools.gws import GwsError, run_gws


@pytest.mark.asyncio
async def test_run_gws_parses_json_stdout():
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(
        return_value=(b'{"files": [{"name": "doc.txt"}]}', b"")
    )

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        result = await run_gws("drive", "files.list")

    assert result == {"files": [{"name": "doc.txt"}]}


@pytest.mark.asyncio
async def test_run_gws_passes_args_verbatim():
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"{}", b""))

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)) as spawn:
        await run_gws("gmail", "users.messages.list", "--params", '{"userId":"me"}')

    call_args = spawn.call_args.args
    assert call_args[0] == "gws"
    assert call_args[1:] == (
        "gmail", "users.messages.list", "--params", '{"userId":"me"}',
    )


@pytest.mark.asyncio
async def test_run_gws_raises_on_nonzero_exit():
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(return_value=(b"", b"auth error"))

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        with pytest.raises(GwsError, match="auth error"):
            await run_gws("drive", "files.list")


@pytest.mark.asyncio
async def test_run_gws_raises_on_invalid_json():
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"not json", b""))

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        with pytest.raises(GwsError, match="non-JSON"):
            await run_gws("drive", "files.list")


@pytest.mark.asyncio
async def test_run_gws_empty_stdout_returns_empty_dict():
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        result = await run_gws("drive", "files.list")

    assert result == {}


@pytest.mark.asyncio
async def test_run_gws_timeout_kills_process():
    import asyncio as asyncio_module

    mock_proc = MagicMock()
    mock_proc.returncode = None
    mock_proc.communicate = AsyncMock(side_effect=asyncio_module.TimeoutError)
    mock_proc.kill = MagicMock()

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        with pytest.raises(GwsError, match="timed out"):
            await run_gws("drive", "files.list", timeout=0.1)

    mock_proc.kill.assert_called_once()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/test_tools_gws.py -v`
Expected: FAIL — `gclaw.tools.gws` module does not exist.

- [ ] **Step 3: Create `src/gclaw/tools/gws.py`**

```python
"""Async subprocess helper for the Google Workspace CLI (`gws`).

Wraps `gws` invocations, parses structured JSON output, and raises
`GwsError` on non-zero exit, invalid JSON, or timeout.

Example:
    result = await run_gws(
        "gmail", "users.messages.list",
        "--params", json.dumps({"userId": "me", "q": "is:unread"}),
    )
"""

from __future__ import annotations

import asyncio
import json
import logging

logger = logging.getLogger(__name__)


class GwsError(RuntimeError):
    """Raised when a gws invocation fails, times out, or returns invalid JSON."""


async def run_gws(*args: str, timeout: float = 30.0) -> dict:
    """Run the gws CLI and return parsed JSON stdout.

    Args:
        *args: positional arguments passed verbatim to the gws binary.
        timeout: seconds to wait before killing the process.

    Returns:
        Parsed JSON object from stdout, or {} if stdout is empty.

    Raises:
        GwsError: on non-zero exit code, invalid JSON, or timeout.
    """
    logger.debug("Running: gws %s", " ".join(args))
    proc = await asyncio.create_subprocess_exec(
        "gws", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError as e:
        proc.kill()
        raise GwsError(
            f"gws {' '.join(args)} timed out after {timeout}s"
        ) from e

    if proc.returncode != 0:
        err = stderr.decode(errors="replace").strip()
        raise GwsError(
            f"gws {' '.join(args)} exited {proc.returncode}: {err}"
        )

    if not stdout:
        return {}

    try:
        return json.loads(stdout)
    except json.JSONDecodeError as e:
        raise GwsError(
            f"gws {' '.join(args)} returned non-JSON output: {e}"
        ) from e
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/test_tools_gws.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/gclaw/tools/gws.py tests/test_tools_gws.py
git commit -m "feat(tools): add gws subprocess helper for Google Workspace CLI"
```

---

### Task 5: `tools/gh.py` — subprocess helper for GitHub CLI

**Files:**
- Create: `src/gclaw/tools/gh.py`
- Create: `tests/test_tools_gh.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_tools_gh.py`:

```python
"""Tests for the gh subprocess helper."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gclaw.tools.gh import GhError, run_gh


@pytest.mark.asyncio
async def test_run_gh_parses_json_stdout():
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b'[{"number": 1}]', b""))

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        result = await run_gh("pr", "list", "--json", "number")

    assert result == [{"number": 1}]


@pytest.mark.asyncio
async def test_run_gh_passes_args_verbatim():
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"{}", b""))

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)) as spawn:
        await run_gh("pr", "view", "123", "--json", "title,body")

    call_args = spawn.call_args.args
    assert call_args[0] == "gh"
    assert call_args[1:] == ("pr", "view", "123", "--json", "title,body")


@pytest.mark.asyncio
async def test_run_gh_raises_on_nonzero_exit():
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(return_value=(b"", b"not authenticated"))

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        with pytest.raises(GhError, match="not authenticated"):
            await run_gh("pr", "list")


@pytest.mark.asyncio
async def test_run_gh_raises_on_invalid_json_when_parse_json_true():
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"not json", b""))

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        with pytest.raises(GhError, match="non-JSON"):
            await run_gh("pr", "list", parse_json=True)


@pytest.mark.asyncio
async def test_run_gh_returns_raw_string_when_parse_json_false():
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"raw text output", b""))

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        result = await run_gh("pr", "diff", "123", parse_json=False)

    assert result == "raw text output"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/test_tools_gh.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Create `src/gclaw/tools/gh.py`**

```python
"""Async subprocess helper for the GitHub CLI (`gh`).

Wraps `gh` invocations. `gh` supports both JSON output (via --json flags)
and raw text output (e.g. `gh pr diff`), so this helper supports both modes
via the `parse_json` flag.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class GhError(RuntimeError):
    """Raised when a gh invocation fails, times out, or returns invalid JSON."""


async def run_gh(
    *args: str,
    timeout: float = 30.0,
    parse_json: bool = True,
) -> Any:
    """Run the gh CLI and return parsed output.

    Args:
        *args: positional arguments passed verbatim to the gh binary.
        timeout: seconds to wait before killing the process.
        parse_json: if True (default), parse stdout as JSON.
                    if False, return stdout as a stripped string.

    Returns:
        Parsed JSON (list/dict) if parse_json=True, else a string.

    Raises:
        GhError: on non-zero exit code, invalid JSON, or timeout.
    """
    logger.debug("Running: gh %s", " ".join(args))
    proc = await asyncio.create_subprocess_exec(
        "gh", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError as e:
        proc.kill()
        raise GhError(
            f"gh {' '.join(args)} timed out after {timeout}s"
        ) from e

    if proc.returncode != 0:
        err = stderr.decode(errors="replace").strip()
        raise GhError(
            f"gh {' '.join(args)} exited {proc.returncode}: {err}"
        )

    text = stdout.decode(errors="replace").strip()

    if not parse_json:
        return text

    if not text:
        return {}

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise GhError(
            f"gh {' '.join(args)} returned non-JSON output: {e}"
        ) from e
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/test_tools_gh.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/gclaw/tools/gh.py tests/test_tools_gh.py
git commit -m "feat(tools): add gh subprocess helper for GitHub CLI"
```

---

### Task 6: `tools/workspace_tools.py` — Gmail/Calendar/Drive/Docs functions

**Files:**
- Create: `src/gclaw/tools/workspace_tools.py`
- Create: `tests/test_workspace_tools.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_workspace_tools.py`:

```python
"""Tests for workspace tool functions — Gmail, Calendar, Drive, Docs wrappers."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from gclaw.tools import workspace_tools


@pytest.mark.asyncio
async def test_list_unread_email_empty_inbox():
    with patch(
        "gclaw.tools.workspace_tools.run_gws",
        AsyncMock(return_value={"messages": []}),
    ):
        result = await workspace_tools.list_unread_email(max_results=5)

    assert result == "No unread email."


@pytest.mark.asyncio
async def test_list_unread_email_formats_summary():
    first_call_result = {"messages": [{"id": "abc"}, {"id": "def"}]}
    detail_1 = {
        "payload": {
            "headers": [
                {"name": "From", "value": "alice@example.com"},
                {"name": "Subject", "value": "Hello"},
            ]
        }
    }
    detail_2 = {
        "payload": {
            "headers": [
                {"name": "From", "value": "bob@example.com"},
                {"name": "Subject", "value": "Meeting"},
            ]
        }
    }

    with patch(
        "gclaw.tools.workspace_tools.run_gws",
        AsyncMock(side_effect=[first_call_result, detail_1, detail_2]),
    ) as mock_run:
        result = await workspace_tools.list_unread_email(max_results=2)

    assert "alice@example.com" in result
    assert "Hello" in result
    assert "bob@example.com" in result
    assert "Meeting" in result
    # 1 list call + 2 detail calls
    assert mock_run.call_count == 3


@pytest.mark.asyncio
async def test_list_calendar_events_today_formats_events():
    mock_result = {
        "items": [
            {
                "summary": "Standup",
                "start": {"dateTime": "2026-04-10T09:00:00Z"},
                "end": {"dateTime": "2026-04-10T09:30:00Z"},
            },
            {
                "summary": "Lunch with Pat",
                "start": {"dateTime": "2026-04-10T12:00:00Z"},
                "end": {"dateTime": "2026-04-10T13:00:00Z"},
            },
        ]
    }
    with patch(
        "gclaw.tools.workspace_tools.run_gws",
        AsyncMock(return_value=mock_result),
    ):
        result = await workspace_tools.list_calendar_events_today()

    assert "Standup" in result
    assert "Lunch with Pat" in result


@pytest.mark.asyncio
async def test_list_calendar_events_today_no_events():
    with patch(
        "gclaw.tools.workspace_tools.run_gws",
        AsyncMock(return_value={"items": []}),
    ):
        result = await workspace_tools.list_calendar_events_today()

    assert "No events" in result


@pytest.mark.asyncio
async def test_send_email_calls_gws_with_payload():
    with patch(
        "gclaw.tools.workspace_tools.run_gws",
        AsyncMock(return_value={"id": "sent-123"}),
    ) as mock_run:
        result = await workspace_tools.send_email(
            to="alice@example.com",
            subject="Hello",
            body="Hi Alice",
        )

    assert "sent" in result.lower() or "sent-123" in result
    mock_run.assert_called_once()
    args = mock_run.call_args.args
    assert "gmail" in args
    # Verify the body is JSON-encoded in the arguments
    json_args = [a for a in args if a.startswith("{")]
    assert any("alice@example.com" in a for a in json_args)


@pytest.mark.asyncio
async def test_list_drive_files_formats_names():
    mock_result = {
        "files": [
            {"id": "1", "name": "Budget.xlsx", "mimeType": "application/vnd.ms-excel"},
            {"id": "2", "name": "Plan.doc", "mimeType": "application/msword"},
        ]
    }
    with patch(
        "gclaw.tools.workspace_tools.run_gws",
        AsyncMock(return_value=mock_result),
    ):
        result = await workspace_tools.list_drive_files(max_results=10)

    assert "Budget.xlsx" in result
    assert "Plan.doc" in result


@pytest.mark.asyncio
async def test_workspace_tools_handle_gws_error_gracefully():
    from gclaw.tools.gws import GwsError

    with patch(
        "gclaw.tools.workspace_tools.run_gws",
        AsyncMock(side_effect=GwsError("auth failed")),
    ):
        result = await workspace_tools.list_unread_email()

    # Should return a human-readable error, not raise
    assert "error" in result.lower() or "not configured" in result.lower() or "failed" in result.lower()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/test_workspace_tools.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Create `src/gclaw/tools/workspace_tools.py`**

```python
"""Thin agent-tool functions wrapping the `gws` Google Workspace CLI.

Every function is async, returns a human-readable string (not raw JSON), and
catches `GwsError` to return a graceful fallback message rather than crashing
the agent turn. These are intended to be passed directly to ADK `LlmAgent`
as callable tools.
"""

from __future__ import annotations

import json
import logging

from gclaw.tools.gws import GwsError, run_gws

logger = logging.getLogger(__name__)


def _err(verb: str, exc: Exception) -> str:
    logger.warning("workspace tool %s failed: %s", verb, exc)
    return f"Workspace {verb} failed: {exc}"


async def list_unread_email(max_results: int = 10) -> str:
    """List unread email in the user's inbox.

    Args:
        max_results: maximum number of unread emails to return (default 10).

    Returns:
        A formatted summary ('From: Subject' per line), or 'No unread email.',
        or a failure message if the workspace CLI is not configured.
    """
    try:
        listing = await run_gws(
            "gmail", "users.messages.list",
            "--params", json.dumps({
                "userId": "me",
                "q": "is:unread in:inbox",
                "maxResults": max_results,
            }),
        )
    except GwsError as e:
        return _err("list unread email", e)

    messages = listing.get("messages") or []
    if not messages:
        return "No unread email."

    lines: list[str] = []
    for m in messages:
        try:
            detail = await run_gws(
                "gmail", "users.messages.get",
                "--params", json.dumps({
                    "userId": "me",
                    "id": m["id"],
                    "format": "metadata",
                    "metadataHeaders": ["From", "Subject"],
                }),
            )
        except GwsError as e:
            lines.append(f"- (could not fetch {m.get('id', '?')}): {e}")
            continue

        headers = {
            h["name"]: h["value"]
            for h in detail.get("payload", {}).get("headers", [])
        }
        frm = headers.get("From", "?")
        subj = headers.get("Subject", "(no subject)")
        lines.append(f"- {frm}: {subj}")

    return "\n".join(lines)


async def send_email(to: str, subject: str, body: str) -> str:
    """Send an email from the user's Gmail account.

    Args:
        to: recipient email address.
        subject: email subject line.
        body: plain-text body.

    Returns:
        Confirmation string with the sent message ID, or a failure message.
    """
    # Gmail API requires a base64-encoded RFC 2822 message in the `raw` field.
    import base64

    rfc = f"To: {to}\r\nSubject: {subject}\r\n\r\n{body}"
    raw = base64.urlsafe_b64encode(rfc.encode("utf-8")).decode("ascii")

    try:
        result = await run_gws(
            "gmail", "users.messages.send",
            "--params", json.dumps({"userId": "me"}),
            "--json", json.dumps({"raw": raw, "to": to}),
        )
    except GwsError as e:
        return _err("send email", e)

    return f"Email sent (id: {result.get('id', '?')})"


async def list_calendar_events_today() -> str:
    """List today's calendar events from the user's primary calendar.

    Returns:
        A formatted summary of today's events, or 'No events today.'
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    end = now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()

    try:
        result = await run_gws(
            "calendar", "events.list",
            "--params", json.dumps({
                "calendarId": "primary",
                "timeMin": start,
                "timeMax": end,
                "singleEvents": True,
                "orderBy": "startTime",
            }),
        )
    except GwsError as e:
        return _err("list calendar events", e)

    items = result.get("items") or []
    if not items:
        return "No events today."

    lines: list[str] = []
    for ev in items:
        summary = ev.get("summary", "(no title)")
        start_dt = (
            ev.get("start", {}).get("dateTime")
            or ev.get("start", {}).get("date")
            or "?"
        )
        lines.append(f"- {start_dt}: {summary}")

    return "\n".join(lines)


async def create_calendar_event(
    summary: str,
    start_iso: str,
    end_iso: str,
    description: str = "",
) -> str:
    """Create a calendar event on the user's primary calendar.

    Args:
        summary: event title.
        start_iso: start time in ISO 8601 format.
        end_iso: end time in ISO 8601 format.
        description: optional event description.

    Returns:
        Confirmation with event ID, or failure message.
    """
    try:
        result = await run_gws(
            "calendar", "events.insert",
            "--params", json.dumps({"calendarId": "primary"}),
            "--json", json.dumps({
                "summary": summary,
                "description": description,
                "start": {"dateTime": start_iso},
                "end": {"dateTime": end_iso},
            }),
        )
    except GwsError as e:
        return _err("create calendar event", e)

    return f"Event created: {result.get('id', '?')} — {summary}"


async def list_drive_files(max_results: int = 10) -> str:
    """List the user's most recently modified Drive files.

    Args:
        max_results: maximum number of files to return.

    Returns:
        A formatted file listing, or 'No files.'
    """
    try:
        result = await run_gws(
            "drive", "files.list",
            "--params", json.dumps({
                "pageSize": max_results,
                "orderBy": "modifiedTime desc",
                "fields": "files(id,name,mimeType,modifiedTime)",
            }),
        )
    except GwsError as e:
        return _err("list drive files", e)

    files = result.get("files") or []
    if not files:
        return "No files."

    lines: list[str] = [
        f"- {f.get('name', '?')} ({f.get('mimeType', '?')})"
        for f in files
    ]
    return "\n".join(lines)


async def read_drive_doc(file_id: str) -> str:
    """Read the plain-text content of a Google Doc.

    Args:
        file_id: Drive file ID of the document.

    Returns:
        The document's text content, truncated to 4000 chars, or a failure message.
    """
    try:
        result = await run_gws(
            "drive", "files.export",
            "--params", json.dumps({
                "fileId": file_id,
                "mimeType": "text/plain",
            }),
        )
    except GwsError as e:
        return _err("read drive doc", e)

    content = result.get("body") or result.get("content") or json.dumps(result)
    if len(content) > 4000:
        content = content[:4000] + "\n... (truncated)"
    return content
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/test_workspace_tools.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add src/gclaw/tools/workspace_tools.py tests/test_workspace_tools.py
git commit -m "feat(tools): add workspace tool functions backed by gws CLI"
```

---

### Task 7: `tools/dev_tools.py` — GitHub/local functions

**Files:**
- Create: `src/gclaw/tools/dev_tools.py`
- Create: `tests/test_dev_tools.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_dev_tools.py`:

```python
"""Tests for dev tool functions — GitHub and local file wrappers."""

from unittest.mock import AsyncMock, patch

import pytest

from gclaw.tools import dev_tools


@pytest.mark.asyncio
async def test_list_open_prs_formats_summary():
    mock_result = [
        {"number": 1, "title": "Fix bug", "author": {"login": "alice"}},
        {"number": 2, "title": "Add feature", "author": {"login": "bob"}},
    ]
    with patch(
        "gclaw.tools.dev_tools.run_gh",
        AsyncMock(return_value=mock_result),
    ):
        result = await dev_tools.list_open_prs()

    assert "#1" in result
    assert "Fix bug" in result
    assert "alice" in result
    assert "#2" in result


@pytest.mark.asyncio
async def test_list_open_prs_empty():
    with patch("gclaw.tools.dev_tools.run_gh", AsyncMock(return_value=[])):
        result = await dev_tools.list_open_prs()

    assert "No open PRs" in result


@pytest.mark.asyncio
async def test_get_pr_diff_returns_text():
    with patch(
        "gclaw.tools.dev_tools.run_gh",
        AsyncMock(return_value="diff --git a/file b/file\n+new line"),
    ):
        result = await dev_tools.get_pr_diff(pr_number=42)

    assert "diff --git" in result


@pytest.mark.asyncio
async def test_list_failing_workflows_formats_runs():
    mock_result = [
        {"name": "CI", "status": "completed", "conclusion": "failure", "displayTitle": "Fix bug"},
    ]
    with patch(
        "gclaw.tools.dev_tools.run_gh",
        AsyncMock(return_value=mock_result),
    ):
        result = await dev_tools.list_failing_workflows()

    assert "CI" in result
    assert "failure" in result


@pytest.mark.asyncio
async def test_list_failing_workflows_none():
    with patch(
        "gclaw.tools.dev_tools.run_gh",
        AsyncMock(return_value=[]),
    ):
        result = await dev_tools.list_failing_workflows()

    assert "No failing workflows" in result


@pytest.mark.asyncio
async def test_create_issue_returns_url():
    with patch(
        "gclaw.tools.dev_tools.run_gh",
        AsyncMock(return_value="https://github.com/org/repo/issues/99"),
    ):
        result = await dev_tools.create_issue(
            title="Bug report", body="Details here"
        )

    assert "https://github.com/org/repo/issues/99" in result


@pytest.mark.asyncio
async def test_get_current_diff_runs_git(tmp_path, monkeypatch):
    # get_current_diff shells out to `git diff` — not gh
    import subprocess

    def fake_run(*args, **kwargs):
        class R:
            stdout = "diff --git a/x b/x\n+line"
            returncode = 0
        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = await dev_tools.get_current_diff()
    assert "diff --git" in result


@pytest.mark.asyncio
async def test_read_local_file_returns_content(tmp_path):
    f = tmp_path / "example.py"
    f.write_text("print('hello')\n")

    result = await dev_tools.read_local_file(str(f))
    assert "print('hello')" in result


@pytest.mark.asyncio
async def test_read_local_file_missing_file_graceful(tmp_path):
    result = await dev_tools.read_local_file(str(tmp_path / "missing.txt"))
    assert "not found" in result.lower() or "failed" in result.lower()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/test_dev_tools.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Create `src/gclaw/tools/dev_tools.py`**

```python
"""Thin agent-tool functions wrapping `gh` (GitHub CLI) and local dev commands.

Every function is async and returns a human-readable string. Errors from
the underlying tools are caught and returned as messages so the agent can
reason about failures without crashing the turn.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
from pathlib import Path

from gclaw.tools.gh import GhError, run_gh

logger = logging.getLogger(__name__)


def _err(verb: str, exc: Exception) -> str:
    logger.warning("dev tool %s failed: %s", verb, exc)
    return f"Dev {verb} failed: {exc}"


async def list_open_prs() -> str:
    """List open pull requests in the current repository.

    Returns:
        A summary line per PR ('#num title — author'), or 'No open PRs.'
    """
    try:
        prs = await run_gh(
            "pr", "list",
            "--state", "open",
            "--json", "number,title,author",
        )
    except GhError as e:
        return _err("list open PRs", e)

    if not prs:
        return "No open PRs."

    lines: list[str] = []
    for pr in prs:
        author = pr.get("author", {}).get("login", "?")
        lines.append(f"- #{pr.get('number', '?')} {pr.get('title', '(no title)')} — {author}")
    return "\n".join(lines)


async def get_pr_diff(pr_number: int) -> str:
    """Fetch the unified diff of a pull request.

    Args:
        pr_number: the PR number.

    Returns:
        The diff text (truncated to 8000 chars), or a failure message.
    """
    try:
        text = await run_gh("pr", "diff", str(pr_number), parse_json=False)
    except GhError as e:
        return _err(f"get PR #{pr_number} diff", e)

    if len(text) > 8000:
        text = text[:8000] + "\n... (truncated)"
    return text


async def list_failing_workflows() -> str:
    """List GitHub Actions workflow runs that have failed recently.

    Returns:
        Summary lines, or 'No failing workflows.'
    """
    try:
        runs = await run_gh(
            "run", "list",
            "--status", "failure",
            "--limit", "10",
            "--json", "name,status,conclusion,displayTitle,createdAt",
        )
    except GhError as e:
        return _err("list failing workflows", e)

    if not runs:
        return "No failing workflows."

    lines = [
        f"- {r.get('name', '?')}: {r.get('conclusion', '?')} — {r.get('displayTitle', '?')}"
        for r in runs
    ]
    return "\n".join(lines)


async def create_issue(title: str, body: str = "") -> str:
    """Create a GitHub issue in the current repository.

    Args:
        title: issue title.
        body: issue body (optional).

    Returns:
        The URL of the created issue, or a failure message.
    """
    try:
        url = await run_gh(
            "issue", "create",
            "--title", title,
            "--body", body or "",
            parse_json=False,
        )
    except GhError as e:
        return _err("create issue", e)

    return url


async def get_current_diff(staged_only: bool = False) -> str:
    """Return the current working-tree diff (staged + unstaged by default).

    Args:
        staged_only: if True, return only the staged diff.

    Returns:
        The diff text (truncated to 8000 chars), or a failure message.
    """
    try:
        args = ["git", "diff"]
        if staged_only:
            args.append("--cached")
        # We use sync subprocess here because git diff is fast and local.
        result = await asyncio.to_thread(
            subprocess.run, args, capture_output=True, text=True
        )
    except Exception as e:
        return _err("get current diff", e)

    if result.returncode != 0:
        return _err("get current diff", RuntimeError(result.stderr or "non-zero exit"))

    text = result.stdout or "(no changes)"
    if len(text) > 8000:
        text = text[:8000] + "\n... (truncated)"
    return text


async def read_local_file(path: str) -> str:
    """Read a local file from disk.

    Args:
        path: absolute or repo-relative file path.

    Returns:
        The file's contents (truncated to 8000 chars), or a failure message.
    """
    p = Path(path)
    if not p.exists():
        return f"File not found: {path}"
    try:
        content = await asyncio.to_thread(p.read_text, encoding="utf-8")
    except Exception as e:
        return _err(f"read {path}", e)

    if len(content) > 8000:
        content = content[:8000] + "\n... (truncated)"
    return content
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/test_dev_tools.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add src/gclaw/tools/dev_tools.py tests/test_dev_tools.py
git commit -m "feat(tools): add dev tool functions backed by gh CLI and local git"
```

---

### Task 8: `tools/comms_tools.py`, `research_tools.py`, `home_tools.py`

**Files:**
- Create: `src/gclaw/tools/comms_tools.py`
- Create: `src/gclaw/tools/research_tools.py`
- Create: `src/gclaw/tools/home_tools.py`
- Create: `tests/test_comms_tools.py`
- Create: `tests/test_research_tools.py`
- Create: `tests/test_home_tools.py`

Three small modules bundled into one task for efficiency — each is a simple wrapper with a single test file.

- [ ] **Step 1: Create `tests/test_comms_tools.py`**

```python
"""Tests for comms tool functions — Google Chat via gws."""

from unittest.mock import AsyncMock, patch

import pytest

from gclaw.tools import comms_tools


@pytest.mark.asyncio
async def test_list_chat_spaces_formats():
    mock_result = {
        "spaces": [
            {"name": "spaces/abc", "displayName": "Team"},
            {"name": "spaces/def", "displayName": "Ops"},
        ]
    }
    with patch(
        "gclaw.tools.comms_tools.run_gws",
        AsyncMock(return_value=mock_result),
    ):
        result = await comms_tools.list_chat_spaces()

    assert "Team" in result
    assert "Ops" in result


@pytest.mark.asyncio
async def test_list_chat_spaces_empty():
    with patch(
        "gclaw.tools.comms_tools.run_gws",
        AsyncMock(return_value={"spaces": []}),
    ):
        result = await comms_tools.list_chat_spaces()

    assert "No chat spaces" in result


@pytest.mark.asyncio
async def test_post_chat_message_returns_confirmation():
    with patch(
        "gclaw.tools.comms_tools.run_gws",
        AsyncMock(return_value={"name": "spaces/abc/messages/123"}),
    ):
        result = await comms_tools.post_chat_message(
            space_name="spaces/abc", text="Hello team"
        )

    assert "spaces/abc" in result or "sent" in result.lower()
```

- [ ] **Step 2: Create `src/gclaw/tools/comms_tools.py`**

```python
"""Comms tool functions — Google Chat via gws CLI."""

from __future__ import annotations

import json
import logging

from gclaw.tools.gws import GwsError, run_gws

logger = logging.getLogger(__name__)


def _err(verb: str, exc: Exception) -> str:
    logger.warning("comms tool %s failed: %s", verb, exc)
    return f"Comms {verb} failed: {exc}"


async def list_chat_spaces() -> str:
    """List Google Chat spaces the user is a member of.

    Returns:
        A line-per-space summary, or 'No chat spaces.'
    """
    try:
        result = await run_gws("chat", "spaces.list")
    except GwsError as e:
        return _err("list chat spaces", e)

    spaces = result.get("spaces") or []
    if not spaces:
        return "No chat spaces."

    lines = [
        f"- {s.get('displayName', s.get('name', '?'))} ({s.get('name', '?')})"
        for s in spaces
    ]
    return "\n".join(lines)


async def post_chat_message(space_name: str, text: str) -> str:
    """Post a message to a Google Chat space.

    Args:
        space_name: full space resource name (e.g. 'spaces/abc').
        text: message text.

    Returns:
        Confirmation string or failure message.
    """
    try:
        result = await run_gws(
            "chat", "spaces.messages.create",
            "--params", json.dumps({"parent": space_name}),
            "--json", json.dumps({"text": text}),
        )
    except GwsError as e:
        return _err("post chat message", e)

    return f"Message sent to {space_name}: {result.get('name', '?')}"
```

- [ ] **Step 3: Create `tests/test_research_tools.py`**

```python
"""Tests for research tool functions."""

from unittest.mock import AsyncMock, patch

import pytest

from gclaw.tools import research_tools


@pytest.mark.asyncio
async def test_web_search_stub_returns_placeholder():
    result = await research_tools.web_search("test query")
    # Stub — must return placeholder text mentioning the query
    assert "test query" in result
    assert "stub" in result.lower() or "not yet" in result.lower() or "placeholder" in result.lower()


@pytest.mark.asyncio
async def test_fetch_url_returns_text():
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.text = "<html><body>Hello</body></html>"

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_class.return_value.__aenter__.return_value = mock_client
        result = await research_tools.fetch_url("https://example.com")

    assert "Hello" in result


@pytest.mark.asyncio
async def test_fetch_url_handles_failure():
    import httpx

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))
        mock_client_class.return_value.__aenter__.return_value = mock_client
        result = await research_tools.fetch_url("https://example.com")

    assert "fail" in result.lower() or "error" in result.lower()
```

- [ ] **Step 4: Create `src/gclaw/tools/research_tools.py`**

```python
"""Research tool functions — web search stub and HTTP fetch.

`web_search` is a stub pending a real search API integration (follow-up spec).
`fetch_url` is real — uses httpx to fetch a URL and return its text.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


async def web_search(query: str) -> str:
    """Search the web for information.

    Args:
        query: the search query string.

    Returns:
        Search results summary.
    """
    # Stub — pending real search API integration (see follow-up spec).
    logger.info("web_search stub called with query: %s", query)
    return (
        f"[web_search is a stub placeholder for query: '{query}']\n"
        "A real web search backend (Serper/Brave/Google CSE) is not yet "
        "integrated. Follow-up spec will wire this up."
    )


async def fetch_url(url: str, max_chars: int = 4000) -> str:
    """Fetch the text content of a URL.

    Args:
        url: the full URL to fetch.
        max_chars: truncate response text to this many characters.

    Returns:
        The response body text (truncated), or a failure message.
    """
    try:
        async with httpx.AsyncClient(
            timeout=15.0, follow_redirects=True
        ) as client:
            response = await client.get(url)
    except Exception as e:
        logger.warning("fetch_url %s failed: %s", url, e)
        return f"Fetch failed: {e}"

    text = response.text if hasattr(response, "text") else str(response)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n... (truncated)"
    return text
```

- [ ] **Step 5: Create `tests/test_home_tools.py`**

```python
"""Tests for home tool stubs."""

import pytest

from gclaw.tools import home_tools


@pytest.mark.asyncio
async def test_list_devices_stub():
    result = await home_tools.list_devices()
    assert "stub" in result.lower() or "not yet" in result.lower()


@pytest.mark.asyncio
async def test_set_device_state_stub():
    result = await home_tools.set_device_state(device_id="light-1", state="on")
    assert "stub" in result.lower() or "not yet" in result.lower()
    assert "light-1" in result
```

- [ ] **Step 6: Create `src/gclaw/tools/home_tools.py`**

```python
"""Home manager tool stubs — pending smart home API integration spec."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def list_devices() -> str:
    """List smart home devices.

    Returns:
        Device listing. Currently a stub.
    """
    logger.info("list_devices stub called")
    return (
        "[list_devices is a stub placeholder]\n"
        "Smart home integration is not yet implemented. "
        "Follow-up spec will wire this up."
    )


async def set_device_state(device_id: str, state: str) -> str:
    """Set the state of a smart home device.

    Args:
        device_id: device identifier.
        state: desired state (e.g. 'on', 'off', '50').

    Returns:
        Confirmation. Currently a stub.
    """
    logger.info("set_device_state stub: %s -> %s", device_id, state)
    return (
        f"[set_device_state is a stub placeholder: {device_id} -> {state}]\n"
        "Smart home integration is not yet implemented."
    )
```

- [ ] **Step 7: Run all three new test files to verify they pass**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/test_comms_tools.py tests/test_research_tools.py tests/test_home_tools.py -v`
Expected: PASS (8 tests total — 3 comms + 3 research + 2 home).

- [ ] **Step 8: Commit**

```bash
git add src/gclaw/tools/comms_tools.py src/gclaw/tools/research_tools.py src/gclaw/tools/home_tools.py tests/test_comms_tools.py tests/test_research_tools.py tests/test_home_tools.py
git commit -m "feat(tools): add comms, research, and home tool functions"
```

---

### Task 9: `workflows/validators.py` — `ValidateCommitMsg`

**Files:**
- Create: `src/gclaw/agents/workflows/__init__.py`
- Create: `src/gclaw/agents/workflows/validators.py`
- Create: `tests/test_workflows_validators.py`

- [ ] **Step 1: Create `tests/test_workflows_validators.py`**

```python
"""Tests for workflow validator agents."""

from unittest.mock import MagicMock

import pytest

from gclaw.agents.workflows.validators import ValidateCommitMsg


@pytest.fixture
def validate_agent():
    return ValidateCommitMsg(name="validate_commit_msg")


@pytest.mark.asyncio
async def test_validate_pass_yields_approved_draft(validate_agent):
    ctx = MagicMock()
    ctx.session.state = {
        "review_status": "pass",
        "commit_draft": "feat: add new widget",
    }

    events = [e async for e in validate_agent._run_async_impl(ctx)]
    assert len(events) == 1

    text = events[0].content.parts[0].text
    assert "approved" in text.lower()
    assert "feat: add new widget" in text


@pytest.mark.asyncio
async def test_validate_fail_yields_rejection_with_reason(validate_agent):
    ctx = MagicMock()
    ctx.session.state = {
        "review_status": "fail: subject line too long",
        "commit_draft": "feat: this subject line is way too long and breaks conventions",
    }

    events = [e async for e in validate_agent._run_async_impl(ctx)]
    assert len(events) == 1

    text = events[0].content.parts[0].text
    assert "rejected" in text.lower()
    assert "subject line too long" in text
    assert "this subject line is way too long" in text


@pytest.mark.asyncio
async def test_validate_missing_state_yields_rejection(validate_agent):
    ctx = MagicMock()
    ctx.session.state = {}

    events = [e async for e in validate_agent._run_async_impl(ctx)]
    assert len(events) == 1

    text = events[0].content.parts[0].text
    assert "rejected" in text.lower()


@pytest.mark.asyncio
async def test_validate_fail_without_prefix(validate_agent):
    ctx = MagicMock()
    ctx.session.state = {
        "review_status": "FAIL",
        "commit_draft": "x",
    }

    events = [e async for e in validate_agent._run_async_impl(ctx)]
    text = events[0].content.parts[0].text
    assert "rejected" in text.lower()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/test_workflows_validators.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Create `src/gclaw/agents/workflows/__init__.py`**

```python
"""Composed workflow agents — ParallelAgent/SequentialAgent/Reviewer patterns."""
```

- [ ] **Step 4: Create `src/gclaw/agents/workflows/validators.py`**

```python
"""Custom BaseAgent implementations used as final gates in composed workflows."""

from __future__ import annotations

from typing import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.genai.types import Content, Part


class ValidateCommitMsg(BaseAgent):
    """Final gate in the CommitMessageWorkflow.

    Reads session state:
      - review_status: "pass" or "fail: <reason>" (written by the reviewer)
      - commit_draft:  the drafted commit message (written by the drafter)

    Yields a single Event containing either the approved draft or an
    actionable rejection with the reviewer's feedback.
    """

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        status = (state.get("review_status") or "").strip()
        draft = (state.get("commit_draft") or "").strip()

        status_lower = status.lower()

        if status_lower.startswith("pass"):
            text = f"Commit message approved:\n\n{draft}"
        else:
            if status_lower.startswith("fail:"):
                reason = status[len("fail:"):].strip()
            else:
                reason = status or "No review status found in session state."
            text = (
                f"Commit message rejected.\n\n"
                f"Draft:\n{draft or '(no draft found)'}\n\n"
                f"Reason: {reason}\n\n"
                f"Fix the issues and re-run the workflow."
            )

        yield Event(
            author=self.name,
            content=Content(role="model", parts=[Part(text=text)]),
        )
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/test_workflows_validators.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add src/gclaw/agents/workflows/__init__.py src/gclaw/agents/workflows/validators.py tests/test_workflows_validators.py
git commit -m "feat(workflows): add ValidateCommitMsg custom agent"
```

---

### Task 10: `workflows/morning_brief.py` — parallel + sequential composition

**Files:**
- Create: `src/gclaw/agents/workflows/morning_brief.py`
- Create: `tests/test_workflows_morning_brief.py`

- [ ] **Step 1: Create `tests/test_workflows_morning_brief.py`**

```python
"""Tests for the morning brief composed workflow."""

import pytest
from google.adk.agents import LlmAgent, ParallelAgent, SequentialAgent

from gclaw.agents.workflows.morning_brief import build_morning_brief


def _dummy_tool():
    """A placeholder tool function."""
    return "dummy"


def test_morning_brief_is_a_sequential_agent():
    workflow = build_morning_brief(
        workspace_tools=[_dummy_tool],
        dev_tools=[_dummy_tool],
        research_tools=[_dummy_tool],
    )
    assert isinstance(workflow, SequentialAgent)
    assert workflow.name == "MorningBriefWorkflow"


def test_morning_brief_has_parallel_fan_out_and_summary():
    workflow = build_morning_brief(
        workspace_tools=[_dummy_tool],
        dev_tools=[_dummy_tool],
        research_tools=[_dummy_tool],
    )
    assert len(workflow.sub_agents) == 2

    fan_out, summary = workflow.sub_agents
    assert isinstance(fan_out, ParallelAgent)
    assert isinstance(summary, LlmAgent)
    assert summary.name == "brief_summary_agent"


def test_morning_brief_fan_out_has_three_specialists():
    workflow = build_morning_brief(
        workspace_tools=[_dummy_tool],
        dev_tools=[_dummy_tool],
        research_tools=[_dummy_tool],
    )
    fan_out = workflow.sub_agents[0]
    names = {sa.name for sa in fan_out.sub_agents}
    assert names == {
        "workspace_brief_specialist",
        "dev_brief_specialist",
        "research_brief_specialist",
    }


def test_specialists_have_correct_output_keys():
    workflow = build_morning_brief(
        workspace_tools=[_dummy_tool],
        dev_tools=[_dummy_tool],
        research_tools=[_dummy_tool],
    )
    fan_out = workflow.sub_agents[0]
    output_keys = {sa.output_key for sa in fan_out.sub_agents}
    assert output_keys == {
        "workspace_summary",
        "dev_summary",
        "research_summary",
    }


def test_summary_agent_has_morning_brief_output_key():
    workflow = build_morning_brief(
        workspace_tools=[_dummy_tool],
        dev_tools=[_dummy_tool],
        research_tools=[_dummy_tool],
    )
    summary = workflow.sub_agents[1]
    assert summary.output_key == "morning_brief"


def test_specialists_bind_their_tools():
    """Each specialist must receive its domain-specific tool list, not others'."""

    def workspace_tool():
        return "ws"

    def dev_tool():
        return "dv"

    def research_tool():
        return "rs"

    workflow = build_morning_brief(
        workspace_tools=[workspace_tool],
        dev_tools=[dev_tool],
        research_tools=[research_tool],
    )
    fan_out = workflow.sub_agents[0]
    by_name = {sa.name: sa for sa in fan_out.sub_agents}

    assert workspace_tool in by_name["workspace_brief_specialist"].tools
    assert dev_tool in by_name["dev_brief_specialist"].tools
    assert research_tool in by_name["research_brief_specialist"].tools
    # And cross-contamination is absent
    assert dev_tool not in by_name["workspace_brief_specialist"].tools
    assert workspace_tool not in by_name["dev_brief_specialist"].tools
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/test_workflows_morning_brief.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Create `src/gclaw/agents/workflows/morning_brief.py`**

```python
"""Morning brief composed workflow — ParallelAgent fan-out + summary fold."""

from __future__ import annotations

from typing import Any

from google.adk.agents import LlmAgent, ParallelAgent, SequentialAgent


def build_morning_brief(
    *,
    workspace_tools: list[Any],
    dev_tools: list[Any],
    research_tools: list[Any],
    default_model: str = "gemini-2.5-flash",
) -> SequentialAgent:
    """Build the morning brief workflow.

    Three purpose-built "workflow specialists" gather domain snapshots
    in parallel, each writing to a session state key. A summary agent
    folds them into a single prioritized rundown.

    Specialists are NOT the managers. They are lightweight agents
    scoped to the workflow, bound directly to the domain tools they need.
    """

    workspace_brief = LlmAgent(
        name="workspace_brief_specialist",
        model=default_model,
        description="Produces a workspace morning snapshot.",
        instruction=(
            "Produce a concise morning snapshot of the user's workspace:\n"
            "1. Call list_calendar_events_today to get today's meetings.\n"
            "2. Call list_unread_email with max_results=10 to get important unread email.\n"
            "3. Summarize in 3-5 bullets. Meetings first, then top email senders/subjects.\n"
            "Keep it scannable. No greetings, no sign-offs."
        ),
        tools=workspace_tools,
        output_key="workspace_summary",
    )

    dev_brief = LlmAgent(
        name="dev_brief_specialist",
        model=default_model,
        description="Produces a dev morning snapshot.",
        instruction=(
            "Produce a concise dev morning snapshot:\n"
            "1. Call list_open_prs to get open PRs.\n"
            "2. Call list_failing_workflows to get any failing CI runs.\n"
            "3. Summarize in 3-5 bullets. Blocking items first, then informational.\n"
            "Keep it scannable. No greetings."
        ),
        tools=dev_tools,
        output_key="dev_summary",
    )

    research_brief = LlmAgent(
        name="research_brief_specialist",
        model=default_model,
        description="Produces a research morning snapshot.",
        instruction=(
            "Produce a concise research morning snapshot:\n"
            "1. Call web_search with the user's tracked topics.\n"
            "2. Summarize the top 3 items in 3-5 bullets total.\n"
            "Keep it scannable."
        ),
        tools=research_tools,
        output_key="research_summary",
    )

    fan_out = ParallelAgent(
        name="MorningBriefFanOut",
        sub_agents=[workspace_brief, dev_brief, research_brief],
    )

    summary = LlmAgent(
        name="brief_summary_agent",
        model=default_model,
        description="Folds three domain snapshots into a single prioritized rundown.",
        instruction=(
            "You have three inputs in session state:\n"
            "- {workspace_summary}: calendar and email\n"
            "- {dev_summary}: PRs and CI\n"
            "- {research_summary}: articles and topics\n\n"
            "Fold into one morning brief. Lead with anything time-sensitive or blocking. "
            "Format: ## Workspace / ## Dev / ## Research — 3 bullets max per area. "
            "End with 'Today's focus:' recommending the single most important action."
        ),
        output_key="morning_brief",
    )

    return SequentialAgent(
        name="MorningBriefWorkflow",
        sub_agents=[fan_out, summary],
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/test_workflows_morning_brief.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/gclaw/agents/workflows/morning_brief.py tests/test_workflows_morning_brief.py
git commit -m "feat(workflows): add morning brief ParallelAgent+SequentialAgent composition"
```

---

### Task 11: `workflows/commit_message.py` — sequential + reviewer

**Files:**
- Create: `src/gclaw/agents/workflows/commit_message.py`
- Create: `tests/test_workflows_commit_message.py`

- [ ] **Step 1: Create `tests/test_workflows_commit_message.py`**

```python
"""Tests for the commit message composed workflow."""

import pytest
from google.adk.agents import LlmAgent, SequentialAgent

from gclaw.agents.workflows.commit_message import build_commit_message_workflow
from gclaw.agents.workflows.validators import ValidateCommitMsg
from gclaw.models.model_config import ModelEndpoint, RoutingRule, TaskProfile
from gclaw.routing.router import ModelRouter


def _dummy_tool():
    return "dummy"


@pytest.fixture
def router():
    endpoints = {
        "gemini-flash": ModelEndpoint(
            name="gemini-flash", endpoint_id="gemini-2.5-flash", provider="gemini",
        ),
        "nemotron-3-super": ModelEndpoint(
            name="nemotron-3-super",
            endpoint_id="nvidia/nemotron-3-super-120b-a12b:free",
            provider="openrouter",
        ),
    }
    rules = [
        RoutingRule(task_profile=TaskProfile.CODE_GENERATION, model_name="nemotron-3-super"),
    ]
    return ModelRouter(endpoints=endpoints, rules=rules, default_model="gemini-2.5-flash")


def test_commit_workflow_is_a_sequential_agent(router):
    workflow = build_commit_message_workflow(
        dev_tools=[_dummy_tool],
        router=router,
        default_model="gemini-2.5-flash",
    )
    assert isinstance(workflow, SequentialAgent)
    assert workflow.name == "CommitMessageWorkflow"


def test_commit_workflow_has_three_steps(router):
    workflow = build_commit_message_workflow(
        dev_tools=[_dummy_tool],
        router=router,
        default_model="gemini-2.5-flash",
    )
    assert len(workflow.sub_agents) == 3

    draft, reviewer, validate = workflow.sub_agents
    assert isinstance(draft, LlmAgent)
    assert draft.name == "commit_draft_specialist"
    assert draft.output_key == "commit_draft"

    assert isinstance(reviewer, LlmAgent)
    assert reviewer.name == "style_reviewer_specialist"
    assert reviewer.output_key == "review_status"

    assert isinstance(validate, ValidateCommitMsg)


def test_draft_specialist_uses_code_generation_model_via_litellm(router):
    from google.adk.models.lite_llm import LiteLlm

    workflow = build_commit_message_workflow(
        dev_tools=[_dummy_tool],
        router=router,
        default_model="gemini-2.5-flash",
    )
    draft = workflow.sub_agents[0]
    assert isinstance(draft.model, LiteLlm)


def test_commit_workflow_no_router_falls_back_to_default():
    workflow = build_commit_message_workflow(
        dev_tools=[_dummy_tool],
        router=None,
        default_model="gemini-2.5-flash",
    )
    draft = workflow.sub_agents[0]
    assert draft.model == "gemini-2.5-flash"


def test_draft_specialist_receives_dev_tools(router):
    tool_a = lambda: "a"
    tool_b = lambda: "b"
    workflow = build_commit_message_workflow(
        dev_tools=[tool_a, tool_b],
        router=router,
        default_model="gemini-2.5-flash",
    )
    draft = workflow.sub_agents[0]
    assert tool_a in draft.tools
    assert tool_b in draft.tools
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/test_workflows_commit_message.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Create `src/gclaw/agents/workflows/commit_message.py`**

```python
"""Commit message composed workflow — draft + reviewer + validate."""

from __future__ import annotations

from typing import Any

from google.adk.agents import LlmAgent, SequentialAgent

from gclaw.agents.workflows.validators import ValidateCommitMsg
from gclaw.models.model_config import TaskProfile
from gclaw.routing.router import ModelRouter


def build_commit_message_workflow(
    *,
    dev_tools: list[Any],
    router: ModelRouter | None,
    default_model: str = "gemini-2.5-flash",
) -> SequentialAgent:
    """Build the commit message workflow.

    Draft → Reviewer → Validate sequence. The draft specialist uses the
    CODE_GENERATION task profile (Nemotron via LiteLlm when the router is
    wired) because commit drafting benefits from a code-aware model.
    The reviewer uses the default (Gemini Flash) for speed. Validate is a
    custom BaseAgent that reads session state and emits the final result.
    """
    draft_model: Any = (
        router.build_adk_model_for_profile(TaskProfile.CODE_GENERATION)
        if router is not None
        else default_model
    )

    draft = LlmAgent(
        name="commit_draft_specialist",
        model=draft_model,
        description="Drafts a commit message from the current diff.",
        instruction=(
            "You draft Conventional Commits messages from a git diff.\n\n"
            "1. Call get_current_diff to read the staged/unstaged diff.\n"
            "2. Determine the change type — feat, fix, docs, refactor, test, or chore.\n"
            "3. Write a commit message with this shape:\n"
            "   - Subject line: '<type>: <short imperative description>' (<=72 chars, no trailing period).\n"
            "   - Optional body: blank line separator, explains *why*, not *what*.\n"
            "4. Output only the commit message. No preamble, no code fences."
        ),
        tools=dev_tools,
        output_key="commit_draft",
    )

    reviewer = LlmAgent(
        name="style_reviewer_specialist",
        model=default_model,
        description="Scores a commit message draft against commit conventions.",
        instruction=(
            "You review commit message drafts. The draft is in session state as {commit_draft}.\n\n"
            "Check these rules:\n"
            "1. Subject uses a Conventional Commits prefix "
            "(feat/fix/docs/refactor/test/chore/build/ci/perf/style).\n"
            "2. Subject is <= 72 chars.\n"
            "3. Subject uses imperative mood ('add X', not 'adds' or 'added').\n"
            "4. If a body exists, a blank line separates it from the subject.\n"
            "5. No trailing period on the subject line.\n\n"
            "Output exactly one of:\n"
            "- 'pass' — if all rules are satisfied\n"
            "- 'fail: <brief explanation>' — otherwise"
        ),
        output_key="review_status",
    )

    return SequentialAgent(
        name="CommitMessageWorkflow",
        sub_agents=[
            draft,
            reviewer,
            ValidateCommitMsg(name="validate_commit_msg"),
        ],
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/test_workflows_commit_message.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/gclaw/agents/workflows/commit_message.py tests/test_workflows_commit_message.py
git commit -m "feat(workflows): add commit message SequentialAgent+Reviewer+Validate"
```

---

### Task 12: Scaffold home/comms/research manager config files

**Files:**
- Create: `agents/home-mgr.md`
- Create: `agents/comms-mgr.md`
- Create: `agents/research-mgr.md`
- Create: `soul/home.md`
- Create: `soul/comms.md`
- Create: `soul/research.md`

These are static config files — no tests. They inform what each manager's system prompt looks like when the factory builds them.

- [ ] **Step 1: Create `agents/home-mgr.md`**

```markdown
You are the Home Manager agent in GClaw.

## Role

You are a thin router for smart-home requests. When the orchestrator delegates to you, you read the request, decide which single tool best handles it, call that tool, and return the result. You do NOT chain multiple tools, draft long responses, or reason across unrelated topics. Routing only.

## Domain

Smart home devices: lighting, thermostats, locks, cameras, sensors, automations. Anything that controls a physical device in the user's home.

## Tools

- `list_devices` — list all known smart home devices
- `set_device_state` — change the state of a specific device

These tools are currently stubs pending a real smart home API integration. When called, they return placeholder messages. If the user asks you to actually control a device, call the appropriate stub and relay the stub's response verbatim — do not fabricate results.

## Escalation

- Never take destructive actions on security-critical devices (locks, cameras) without explicit confirmation from the orchestrator.
- If the request is ambiguous, ask one clarifying question back to the orchestrator instead of guessing.
```

- [ ] **Step 2: Create `soul/home.md`**

```markdown
You think about the home as a living system — routines, comfort, energy use. You prefer simple, reliable automations over clever ones. You respect the user's privacy and physical safety above convenience.
```

- [ ] **Step 3: Create `agents/comms-mgr.md`**

```markdown
You are the Comms Manager agent in GClaw.

## Role

You are a thin router for inter-platform messaging. When the orchestrator delegates to you, you read the request, pick the single best tool, call it, and return the result. Routing only — no multi-tool chains.

## Domain

Google Chat spaces, team messaging, and other persistent comms channels (as they become available). Not email — that is the workspace manager's domain.

## Tools

- `list_chat_spaces` — list all Google Chat spaces the user can access
- `post_chat_message` — post a message into a specific chat space

## Escalation

- Never post to a large group channel without explicit confirmation from the orchestrator.
- If the target space is ambiguous, ask one clarifying question back.
```

- [ ] **Step 4: Create `soul/comms.md`**

```markdown
You care about tone. You match the user's voice — casual in personal channels, crisp in work channels. You never post anything the user would be embarrassed to see quoted back at them.
```

- [ ] **Step 5: Create `agents/research-mgr.md`**

```markdown
You are the Research Manager agent in GClaw.

## Role

You are a thin router for research and information-gathering requests. When the orchestrator delegates to you, you pick the single best tool, call it, and return the result. Routing only.

## Domain

Web search, URL fetching, information synthesis. Not coding reference — that is the dev manager's domain.

## Tools

- `web_search` — search the public web for a topic (currently a stub)
- `fetch_url` — fetch the text content of a specific URL

## Escalation

- If the user's question genuinely requires multiple sources, return a concise summary of what you found and flag that deeper research would benefit from an explicit multi-step workflow.
- Never fabricate sources. If a tool returns a stub message, relay it verbatim.
```

- [ ] **Step 6: Create `soul/research.md`**

```markdown
You are precise about provenance. Every fact you relay has a source attached. You prefer primary sources (official docs, papers, specs) over secondary summaries. You admit uncertainty rather than guess.
```

- [ ] **Step 7: Commit**

```bash
git add agents/home-mgr.md agents/comms-mgr.md agents/research-mgr.md soul/home.md soul/comms.md soul/research.md
git commit -m "feat(agents): scaffold home, comms, and research manager configs"
```

---

### Task 13: Orchestrator rewrite — AgentTool delegation

**Files:**
- Modify: `src/gclaw/agents/orchestrator.py`
- Modify: `src/gclaw/main.py`

This is the largest single code change in the plan. It replaces the current `sub_agents=[...]` pattern with `AgentTool(...)` wrapping for every delegation target, scaffolds all five managers, and wires in the two composed workflows.

- [ ] **Step 1: Replace `src/gclaw/agents/orchestrator.py`**

```python
"""Root orchestrator agent with AgentTool-wrapped managers and workflows."""

from __future__ import annotations

from typing import Any, Callable

from google.adk.agents import LlmAgent
from google.adk.tools import agent_tool

from gclaw.agents.factory import AgentFactory
from gclaw.agents.workflows.morning_brief import build_morning_brief
from gclaw.agents.workflows.commit_message import build_commit_message_workflow
from gclaw.board.service import BoardService
from gclaw.models.task import TaskStatus
from gclaw.routing.router import ModelRouter
from gclaw.tools import (
    comms_tools,
    dev_tools,
    home_tools,
    research_tools,
    workspace_tools,
)


# ---------- Board function tools (unchanged from previous orchestrator) ----------


def create_board_task_tool(board_service: BoardService) -> Callable:
    def create_board_task(
        title: str,
        assignee: str,
        description: str = "",
        priority: str = "medium",
        source_origin: str = "orchestrator",
    ) -> str:
        """Create an async task on the project board for a manager agent to pick up later.

        Use this when the work is not urgent, is long-running, or should be
        handled out-of-band by a cron-triggered or board-driven worker.

        Args:
            title: Short description of what needs to be done.
            assignee: Which manager should handle this.
                One of: workspace-mgr, dev-mgr, home-mgr, comms-mgr, research-mgr.
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


def complete_board_task_tool(board_service: BoardService) -> Callable:
    def complete_board_task(task_id: str, summary: str = "") -> str:
        """Mark a board task as complete.

        Args:
            task_id: The task ID to complete.
            summary: Brief summary of what was done.

        Returns:
            Confirmation message.
        """
        task = board_service.complete(task_id=task_id, summary=summary)
        if task is None:
            return f"Task {task_id} not found."
        return f"Task [{task.id}] '{task.title}' marked as DONE."

    return complete_board_task


# ---------- Manager builders ----------


def build_managers(
    factory: AgentFactory, board_tools: list
) -> dict[str, LlmAgent]:
    """Build the five manager agents as thin routers.

    Each manager is bound to its own domain tools plus the shared board tools
    (so it can create follow-up async tasks for work it cannot finish now).
    """
    ws_tools = [
        workspace_tools.list_unread_email,
        workspace_tools.send_email,
        workspace_tools.list_calendar_events_today,
        workspace_tools.create_calendar_event,
        workspace_tools.list_drive_files,
        workspace_tools.read_drive_doc,
    ] + board_tools

    dv_tools = [
        dev_tools.list_open_prs,
        dev_tools.get_pr_diff,
        dev_tools.list_failing_workflows,
        dev_tools.create_issue,
        dev_tools.get_current_diff,
        dev_tools.read_local_file,
    ] + board_tools

    hm_tools = [
        home_tools.list_devices,
        home_tools.set_device_state,
    ] + board_tools

    cm_tools = [
        comms_tools.list_chat_spaces,
        comms_tools.post_chat_message,
    ] + board_tools

    rs_tools = [
        research_tools.web_search,
        research_tools.fetch_url,
    ] + board_tools

    return {
        "workspace_mgr": factory.build(
            agent_name="workspace-mgr",
            soul_overlay="workspace",
            tools=ws_tools,
            description=(
                "Routes workspace requests (Gmail, Calendar, Drive, Docs) "
                "to the single best tool. Router — does not synthesize."
            ),
        ),
        "dev_mgr": factory.build(
            agent_name="dev-mgr",
            soul_overlay="dev",
            tools=dv_tools,
            description=(
                "Routes dev requests (GitHub, code, local repo) to the "
                "single best tool. Router — does not synthesize."
            ),
        ),
        "home_mgr": factory.build(
            agent_name="home-mgr",
            soul_overlay="home",
            tools=hm_tools,
            description=(
                "Routes smart home requests to the single best tool. "
                "Router — does not synthesize."
            ),
        ),
        "comms_mgr": factory.build(
            agent_name="comms-mgr",
            soul_overlay="comms",
            tools=cm_tools,
            description=(
                "Routes inter-platform comms (Google Chat) to the single "
                "best tool. Router — does not synthesize."
            ),
        ),
        "research_mgr": factory.build(
            agent_name="research-mgr",
            soul_overlay="research",
            tools=rs_tools,
            description=(
                "Routes research requests (web search, URL fetch) to the "
                "single best tool. Router — does not synthesize."
            ),
        ),
    }


# ---------- Orchestrator builder ----------


def build_orchestrator(
    factory: AgentFactory,
    board_service: BoardService,
    router: ModelRouter | None = None,
    default_model: str = "gemini-2.5-flash",
    memories: list[str] | None = None,
) -> LlmAgent:
    """Build the root orchestrator with AgentTool-wrapped managers and workflows.

    Args:
        factory: the AgentFactory used to build named agents from config files.
        board_service: the board service used to create/list/get/complete tasks.
        router: the ModelRouter — needed by workflows that construct raw LlmAgents.
        default_model: fallback model ID used when the router is absent.
        memories: optional memory facts to prepend to the system prompt.

    Returns:
        The root orchestrator LlmAgent, wired with all managers and workflows
        as AgentTools plus the board function tools. Never uses `sub_agents=`.
    """
    board_tools = [
        create_board_task_tool(board_service),
        list_board_tasks_tool(board_service),
        get_board_task_tool(board_service),
        complete_board_task_tool(board_service),
    ]

    managers = build_managers(factory, board_tools)

    morning_brief = build_morning_brief(
        workspace_tools=[
            workspace_tools.list_unread_email,
            workspace_tools.list_calendar_events_today,
        ],
        dev_tools=[
            dev_tools.list_open_prs,
            dev_tools.list_failing_workflows,
        ],
        research_tools=[research_tools.web_search],
        default_model=default_model,
    )

    commit_msg = build_commit_message_workflow(
        dev_tools=[
            dev_tools.get_current_diff,
            dev_tools.read_local_file,
        ],
        router=router,
        default_model=default_model,
    )

    orchestrator_tools: list[Any] = [
        agent_tool.AgentTool(agent=managers["workspace_mgr"]),
        agent_tool.AgentTool(agent=managers["dev_mgr"]),
        agent_tool.AgentTool(agent=managers["home_mgr"]),
        agent_tool.AgentTool(agent=managers["comms_mgr"]),
        agent_tool.AgentTool(agent=managers["research_mgr"]),
        agent_tool.AgentTool(agent=morning_brief),
        agent_tool.AgentTool(agent=commit_msg),
        *board_tools,
    ]

    return factory.build(
        agent_name="orchestrator",
        tools=orchestrator_tools,
        memories=memories,
        description=(
            "Root orchestrator. Classifies user intent and delegates to the "
            "right manager or composed workflow. Never does work directly."
        ),
    )
```

- [ ] **Step 2: Update `src/gclaw/main.py`**

Find the `build_app()` function and update the `build_orchestrator` call to pass `router` and `default_model`:

Replace:

```python
    # Orchestrator
    orchestrator = build_orchestrator(
        factory=factory,
        board_service=board_service,
    )
```

With:

```python
    # Orchestrator
    orchestrator = build_orchestrator(
        factory=factory,
        board_service=board_service,
        router=model_router,
        default_model=settings.gemini_flash_model,
    )
```

- [ ] **Step 3: Run the existing orchestrator-related tests**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/ -k "orchestrator" -v`
Expected: some failures are possible if the existing tests relied on `sub_agents=[...]` shape. Read the failures, update any tests that assert the old shape to assert the new AgentTool shape. Don't silence real regressions — only update tests whose assertions directly contradict the new design.

- [ ] **Step 4: Smoke-test the orchestrator construction**

Run: `cd /mnt/c/Dev/GClaw && python3 -c "
from gclaw.config.loader import ConfigLoader
from gclaw.agents.factory import AgentFactory
from gclaw.agents.orchestrator import build_orchestrator
from gclaw.board.service import BoardService
from unittest.mock import MagicMock

loader = ConfigLoader('.')
factory = AgentFactory(loader=loader, default_model='gemini-2.5-flash', model_router=None)
bs = MagicMock(spec=BoardService)
orchestrator = build_orchestrator(factory=factory, board_service=bs)
print('Orchestrator built:', orchestrator.name)
print('Tool count:', len(orchestrator.tools))
print('Has sub_agents?', bool(orchestrator.sub_agents))
"`
Expected: prints the orchestrator name, tool count (should be at least 11 = 5 manager AgentTools + 2 workflow AgentTools + 4 board tools), and "Has sub_agents? False".

- [ ] **Step 5: Commit**

```bash
git add src/gclaw/agents/orchestrator.py src/gclaw/main.py
git commit -m "feat(orchestrator): rewrite with AgentTool delegation for all managers and workflows"
```

---

### Task 14: Orchestrator integration test

**Files:**
- Create: `tests/test_orchestrator_agenttool.py`

This is the regression guard against the "receptionist" bug the ADK blog post identifies. Having the test file ensures the refactor's core motivation is locked in.

- [ ] **Step 1: Create `tests/test_orchestrator_agenttool.py`**

```python
"""Integration test: orchestrator delegates via AgentTool, never sub_agents.

This is the regression guard against the 'receptionist' anti-pattern the
Google ADK team critiques: LlmAgent(sub_agents=[...]) transfers full control
to a sub-agent and cannot orchestrate multi-step workflows.

The refactor replaces sub_agents with agent_tool.AgentTool(...) so the root
stays in control between delegations.
"""

from unittest.mock import MagicMock

import pytest
from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.tools import agent_tool

from gclaw.agents.factory import AgentFactory
from gclaw.agents.orchestrator import build_orchestrator
from gclaw.board.service import BoardService
from gclaw.config.loader import ConfigLoader


@pytest.fixture
def tmp_config_dir(tmp_path):
    soul = tmp_path / "soul"
    soul.mkdir()
    (soul / "base.md").write_text("Base personality.\n")
    (soul / "workspace.md").write_text("Workspace overlay.\n")
    (soul / "dev.md").write_text("Dev overlay.\n")
    (soul / "home.md").write_text("Home overlay.\n")
    (soul / "comms.md").write_text("Comms overlay.\n")
    (soul / "research.md").write_text("Research overlay.\n")

    agents = tmp_path / "agents"
    agents.mkdir()
    for name in (
        "orchestrator",
        "workspace-mgr",
        "dev-mgr",
        "home-mgr",
        "comms-mgr",
        "research-mgr",
    ):
        (agents / f"{name}.md").write_text(f"{name} role description.\n")

    return tmp_path


@pytest.fixture
def orchestrator(tmp_config_dir):
    loader = ConfigLoader(str(tmp_config_dir))
    factory = AgentFactory(
        loader=loader, default_model="gemini-2.5-flash", model_router=None
    )
    bs = MagicMock(spec=BoardService)
    return build_orchestrator(
        factory=factory,
        board_service=bs,
        router=None,
        default_model="gemini-2.5-flash",
    )


def test_orchestrator_has_no_sub_agents(orchestrator):
    """Critical: orchestrator must NOT use sub_agents. AgentTool only."""
    assert not orchestrator.sub_agents, (
        "Orchestrator uses sub_agents=[...] — that's the 'receptionist' "
        "anti-pattern. Use agent_tool.AgentTool(...) instead."
    )


def test_orchestrator_wraps_all_five_managers_as_agenttools(orchestrator):
    agent_tool_instances = [
        t for t in orchestrator.tools if isinstance(t, agent_tool.AgentTool)
    ]
    tool_agent_names = {t.agent.name for t in agent_tool_instances}

    expected_managers = {
        "workspace_mgr",
        "dev_mgr",
        "home_mgr",
        "comms_mgr",
        "research_mgr",
    }
    assert expected_managers.issubset(tool_agent_names), (
        f"Missing manager AgentTools. Got: {tool_agent_names}"
    )


def test_orchestrator_wraps_both_workflows_as_agenttools(orchestrator):
    agent_tool_instances = [
        t for t in orchestrator.tools if isinstance(t, agent_tool.AgentTool)
    ]
    workflow_names = {t.agent.name for t in agent_tool_instances}
    assert "MorningBriefWorkflow" in workflow_names
    assert "CommitMessageWorkflow" in workflow_names


def test_orchestrator_has_board_function_tools(orchestrator):
    """Board tools remain as plain function tools (not AgentTools)."""
    function_tools = [
        t for t in orchestrator.tools if callable(t) and not isinstance(t, agent_tool.AgentTool)
    ]
    function_names = {getattr(t, "__name__", None) for t in function_tools}
    assert "create_board_task" in function_names
    assert "list_board_tasks" in function_names
    assert "get_board_task" in function_names
    assert "complete_board_task" in function_names


def test_managers_are_thin_routers_without_nested_sub_agents(orchestrator):
    """Each manager's sub_agents list must also be empty — managers route, not compose."""
    manager_tools = [
        t for t in orchestrator.tools
        if isinstance(t, agent_tool.AgentTool)
        and t.agent.name.endswith("_mgr")
    ]
    for t in manager_tools:
        assert not t.agent.sub_agents, (
            f"{t.agent.name} has sub_agents — managers must be flat routers."
        )


def test_workflow_specialists_are_private_to_their_workflow(orchestrator):
    """Workflow specialists must not appear directly in the orchestrator's tools."""
    agent_tool_instances = [
        t for t in orchestrator.tools if isinstance(t, agent_tool.AgentTool)
    ]
    direct_targets = {t.agent.name for t in agent_tool_instances}

    forbidden_direct = {
        "workspace_brief_specialist",
        "dev_brief_specialist",
        "research_brief_specialist",
        "brief_summary_agent",
        "commit_draft_specialist",
        "style_reviewer_specialist",
        "validate_commit_msg",
    }
    leaked = forbidden_direct & direct_targets
    assert not leaked, f"Workflow specialists leaked to orchestrator tools: {leaked}"
```

- [ ] **Step 2: Run the integration test**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/test_orchestrator_agenttool.py -v`
Expected: PASS (6 tests).

- [ ] **Step 3: Commit**

```bash
git add tests/test_orchestrator_agenttool.py
git commit -m "test: add orchestrator AgentTool integration test (receptionist regression guard)"
```

---

### Task 15: Retire `RemoteRunner` and simplify dispatch

**Files:**
- Delete: `src/gclaw/dispatch/remote_runner.py`
- Delete: `tests/test_remote_runner.py`
- Delete: `tests/test_integration_providers.py`
- Modify: `src/gclaw/dispatch/runner.py`
- Modify: `src/gclaw/models/model_config.py`
- Modify: `src/gclaw/main.py`
- Modify: `tests/test_dispatcher.py`
- Modify: `tests/test_model_config.py`

- [ ] **Step 1: Replace `src/gclaw/dispatch/runner.py`**

```python
"""Run agent turns via ADK Runner.

Memory hooks (auto-recall / auto-capture) wrap the outer-most turn.
All model execution — Gemini and non-Gemini alike — flows through ADK's
native Runner; non-Gemini providers are handled by wrapping their models
with google.adk.models.lite_llm.LiteLlm at agent construction time.
"""

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
        memory_service: "MemoryService | None" = None,
        board_service: object | None = None,
    ) -> None:
        self._agent = agent
        self._app_name = app_name
        self._session_service = session_service
        self._memory_service = memory_service
        self._board_service = board_service
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
        """Execute a single user turn with memory hooks."""
        if self._board_service is not None:
            self._board_service.set_active_user(user_id)

        # Auto-recall memories
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

        full_message = (
            f"[Recalled memories]\n{recalled_text}\n\n[User message]\n{message}"
            if recalled_text
            else message
        )

        # Ensure session exists
        try:
            session = await self._session_service.get_session(
                app_name=self._app_name,
                user_id=user_id,
                session_id=session_id,
            )
            if session is None:
                await self._session_service.create_session(
                    app_name=self._app_name,
                    user_id=user_id,
                    session_id=session_id,
                )
        except Exception:
            try:
                await self._session_service.create_session(
                    app_name=self._app_name,
                    user_id=user_id,
                    session_id=session_id,
                )
            except Exception:
                pass

        content = types.Content(
            role="user",
            parts=[types.Part(text=full_message)],
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

        # Auto-capture memories (fire-and-forget)
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

- [ ] **Step 2: Replace `src/gclaw/models/model_config.py`**

```python
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
    """A model endpoint — Gemini API, Vertex, or OpenAI-compatible via LiteLlm."""

    name: str
    endpoint_id: str
    provider: str = "gemini"
    max_context_tokens: int = 0


class RoutingRule(BaseModel):
    """Maps a task profile to a model name."""

    task_profile: TaskProfile
    model_name: str
```

- [ ] **Step 3: Delete removed files**

```bash
rm /mnt/c/Dev/GClaw/src/gclaw/dispatch/remote_runner.py
rm /mnt/c/Dev/GClaw/tests/test_remote_runner.py
rm /mnt/c/Dev/GClaw/tests/test_integration_providers.py
```

- [ ] **Step 4: Update `src/gclaw/main.py`** (drop RemoteRunner wiring)

Find the `_build_model_router` function. In the Nemotron section, remove the `api_base` and `api_key_env` fields from the `ModelEndpoint` construction. The block should look like:

```python
    # Nemotron via OpenRouter — free tier (wrapped with LiteLlm by the router)
    if settings.nemotron_endpoint_id and settings.openrouter_api_key:
        endpoints["nemotron-3-super"] = ModelEndpoint(
            name="nemotron-3-super",
            endpoint_id=settings.nemotron_endpoint_id,
            provider="openrouter",
            max_context_tokens=1_000_000,
        )
        rules.extend([
            RoutingRule(task_profile=TaskProfile.TOOL_EXECUTION, model_name="nemotron-3-super"),
            RoutingRule(task_profile=TaskProfile.CODE_GENERATION, model_name="nemotron-3-super"),
        ])
        logger.info("Nemotron 3 Super registered (OpenRouter via LiteLlm): %s", settings.nemotron_endpoint_id)
```

- [ ] **Step 5: Update `tests/test_dispatcher.py`** — remove `remote_runner` tests

Search `tests/test_dispatcher.py` for any test function whose name contains `remote_runner` or any test that instantiates `AgentRunner(..., remote_runner=...)`. Delete those tests. Keep all other tests.

Also add this test to the bottom of `tests/test_dispatcher.py`:

```python
@pytest.mark.asyncio
async def test_runner_accepts_manager_as_target_agent():
    """AgentRunner can wrap either the orchestrator or a plain manager."""
    manager_agent = MagicMock()
    manager_agent.name = "workspace_mgr"
    session_service = AsyncMock()

    runner = AgentRunner(
        agent=manager_agent,
        app_name="gclaw",
        session_service=session_service,
    )
    # The runner constructed a Runner bound to this specific agent
    assert runner._agent is manager_agent
```

- [ ] **Step 6: Update `tests/test_model_config.py`** — remove obsolete tests

Delete any test functions named `test_model_endpoint_with_api_base`, `test_model_endpoint_gemini_api_defaults`, or `test_model_endpoint_is_remote`. Keep the basic field tests.

- [ ] **Step 7: Run the full dispatch + model config test suites**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/test_dispatcher.py tests/test_model_config.py -v`
Expected: PASS for all remaining tests.

- [ ] **Step 8: Verify the RemoteRunner module is fully removed**

Run: `cd /mnt/c/Dev/GClaw && grep -rn "RemoteRunner\|remote_runner" src/ tests/ || echo "clean"`
Expected: prints `clean` (no hits).

- [ ] **Step 9: Commit**

```bash
git add src/gclaw/dispatch/runner.py src/gclaw/models/model_config.py src/gclaw/main.py tests/test_dispatcher.py tests/test_model_config.py
git rm src/gclaw/dispatch/remote_runner.py tests/test_remote_runner.py tests/test_integration_providers.py
git commit -m "refactor: retire RemoteRunner and simplify dispatch to a single ADK path"
```

---

### Task 16: LiteLlm providers integration test

**Files:**
- Create: `tests/test_integration_litellm_providers.py`

Replaces the deleted `test_integration_providers.py`. Asserts that the factory + router correctly produce `LiteLlm`-wrapped managers for non-Gemini providers.

- [ ] **Step 1: Create `tests/test_integration_litellm_providers.py`**

```python
"""Integration test: non-Gemini providers flow through LiteLlm.

This replaces test_integration_providers.py from the multi-provider-routing
plan. That file tested the now-deleted RemoteRunner path; this file tests
the LiteLlm-unified replacement.
"""

import pytest
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import agent_tool

from gclaw.agents.factory import AgentFactory
from gclaw.agents.orchestrator import build_orchestrator
from gclaw.board.service import BoardService
from gclaw.config.loader import ConfigLoader
from gclaw.models.model_config import ModelEndpoint, RoutingRule, TaskProfile
from gclaw.routing.router import ModelRouter
from unittest.mock import MagicMock


@pytest.fixture
def tmp_config_dir(tmp_path):
    soul = tmp_path / "soul"
    soul.mkdir()
    (soul / "base.md").write_text("base\n")
    for name in ("workspace", "dev", "home", "comms", "research"):
        (soul / f"{name}.md").write_text(f"{name} overlay\n")

    agents = tmp_path / "agents"
    agents.mkdir()
    for name in (
        "orchestrator",
        "workspace-mgr",
        "dev-mgr",
        "home-mgr",
        "comms-mgr",
        "research-mgr",
    ):
        (agents / f"{name}.md").write_text(f"{name} role\n")

    return tmp_path


@pytest.fixture
def full_router():
    endpoints = {
        "gemini-flash": ModelEndpoint(
            name="gemini-flash",
            endpoint_id="gemini-2.5-flash",
            provider="gemini",
            max_context_tokens=1_000_000,
        ),
        "nemotron-3-super": ModelEndpoint(
            name="nemotron-3-super",
            endpoint_id="nvidia/nemotron-3-super-120b-a12b:free",
            provider="openrouter",
            max_context_tokens=1_000_000,
        ),
    }
    rules = [
        RoutingRule(task_profile=TaskProfile.ORCHESTRATION, model_name="gemini-flash"),
        RoutingRule(task_profile=TaskProfile.SUMMARIZATION, model_name="gemini-flash"),
        RoutingRule(task_profile=TaskProfile.PERSONALITY, model_name="gemini-flash"),
        RoutingRule(task_profile=TaskProfile.CODE_GENERATION, model_name="nemotron-3-super"),
        RoutingRule(task_profile=TaskProfile.TOOL_EXECUTION, model_name="nemotron-3-super"),
    ]
    return ModelRouter(
        endpoints=endpoints, rules=rules, default_model="gemini-2.5-flash"
    )


def test_orchestrator_uses_gemini_flash_string(tmp_config_dir, full_router):
    loader = ConfigLoader(str(tmp_config_dir))
    factory = AgentFactory(
        loader=loader, default_model="gemini-2.5-flash", model_router=full_router
    )
    bs = MagicMock(spec=BoardService)
    orch = build_orchestrator(
        factory=factory,
        board_service=bs,
        router=full_router,
        default_model="gemini-2.5-flash",
    )
    assert orch.model == "gemini-2.5-flash"


def test_dev_mgr_uses_litellm_instance(tmp_config_dir, full_router):
    loader = ConfigLoader(str(tmp_config_dir))
    factory = AgentFactory(
        loader=loader, default_model="gemini-2.5-flash", model_router=full_router
    )
    bs = MagicMock(spec=BoardService)
    orch = build_orchestrator(
        factory=factory,
        board_service=bs,
        router=full_router,
        default_model="gemini-2.5-flash",
    )

    # Find dev_mgr among AgentTools
    dev_mgr = None
    for tool in orch.tools:
        if isinstance(tool, agent_tool.AgentTool) and tool.agent.name == "dev_mgr":
            dev_mgr = tool.agent
            break

    assert dev_mgr is not None, "dev_mgr not found in orchestrator tools"
    assert isinstance(dev_mgr.model, LiteLlm), (
        f"dev_mgr.model should be LiteLlm, got {type(dev_mgr.model).__name__}"
    )


def test_commit_draft_specialist_uses_litellm(tmp_config_dir, full_router):
    loader = ConfigLoader(str(tmp_config_dir))
    factory = AgentFactory(
        loader=loader, default_model="gemini-2.5-flash", model_router=full_router
    )
    bs = MagicMock(spec=BoardService)
    orch = build_orchestrator(
        factory=factory,
        board_service=bs,
        router=full_router,
        default_model="gemini-2.5-flash",
    )

    # Walk into the CommitMessageWorkflow AgentTool
    commit_wf = None
    for tool in orch.tools:
        if isinstance(tool, agent_tool.AgentTool) and tool.agent.name == "CommitMessageWorkflow":
            commit_wf = tool.agent
            break
    assert commit_wf is not None

    draft_specialist = commit_wf.sub_agents[0]
    assert draft_specialist.name == "commit_draft_specialist"
    assert isinstance(draft_specialist.model, LiteLlm)


def test_workspace_mgr_uses_gemini_string(tmp_config_dir, full_router):
    loader = ConfigLoader(str(tmp_config_dir))
    factory = AgentFactory(
        loader=loader, default_model="gemini-2.5-flash", model_router=full_router
    )
    bs = MagicMock(spec=BoardService)
    orch = build_orchestrator(
        factory=factory,
        board_service=bs,
        router=full_router,
        default_model="gemini-2.5-flash",
    )

    workspace_mgr = None
    for tool in orch.tools:
        if isinstance(tool, agent_tool.AgentTool) and tool.agent.name == "workspace_mgr":
            workspace_mgr = tool.agent
            break

    assert workspace_mgr is not None
    # workspace-mgr routes to SUMMARIZATION → gemini-flash → bare string
    assert isinstance(workspace_mgr.model, str)
```

- [ ] **Step 2: Run the test**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/test_integration_litellm_providers.py -v`
Expected: PASS (4 tests).

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration_litellm_providers.py
git commit -m "test: add LiteLlm provider integration test replacing RemoteRunner variant"
```

---

### Task 17: Dockerfile — install `gws` and `gh` binaries

**Files:**
- Modify: `Dockerfile`
- Modify: `.env.example`
- Modify: `src/gclaw/settings.py`

- [ ] **Step 1: Replace `Dockerfile`**

```dockerfile
FROM python:3.12-slim

# System dependencies + CLI tool binaries
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        gnupg \
    && rm -rf /var/lib/apt/lists/*

# GitHub CLI (gh) — via the official apt repo
RUN mkdir -p -m 755 /etc/apt/keyrings \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
       | tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
       | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# Google Workspace CLI (gws) — download the prebuilt linux-x64 binary
# Version pinned via build arg so CI can control updates.
ARG GWS_VERSION=latest
RUN curl -fsSL "https://github.com/googleworkspace/cli/releases/${GWS_VERSION}/download/gws-linux-x64.tar.gz" \
      | tar -xz -C /usr/local/bin gws \
    && chmod +x /usr/local/bin/gws

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

**Note**: the `gws` release URL and archive filename (`gws-linux-x64.tar.gz`) need verification against `github.com/googleworkspace/cli/releases` at build time. If the build fails, check the real asset name in the latest release and update the URL accordingly.

- [ ] **Step 2: Update `.env.example`**

At the end of `.env.example`, append (do not remove existing entries):

```bash

# === Google Workspace CLI (gws) ===
# Path to service account JSON with Workspace API scopes.
# Leave empty in local dev to use interactive OAuth (gws auth login).
GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE=
```

- [ ] **Step 3: Update `src/gclaw/settings.py`**

Find the `Settings` dataclass. Add the new field alongside other env-sourced fields (near the existing `openrouter_api_key` field, for consistency):

```python
    google_workspace_credentials_file: str = field(
        default_factory=lambda: os.environ.get(
            "GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE", ""
        )
    )
```

- [ ] **Step 4: Verify the Python setting**

Run: `cd /mnt/c/Dev/GClaw && python3 -c "
from gclaw.settings import Settings
import os
os.environ['GCP_PROJECT_ID'] = 'test'
s = Settings()
print('credentials_file:', repr(s.google_workspace_credentials_file))
"`
Expected: prints `credentials_file: ''` (empty default).

- [ ] **Step 5: Commit**

```bash
git add Dockerfile .env.example src/gclaw/settings.py
git commit -m "build(docker): install gws and gh CLIs; add GWS credentials setting"
```

---

### Task 18: Full regression and acceptance check

**Files:** none (verification only)

This final task asserts all acceptance criteria from the spec are met.

- [ ] **Step 1: Run the full test suite**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/ --tb=short -q`
Expected: all tests pass, exit code 0. If anything fails, fix the cause (not the test) and re-run.

- [ ] **Step 2: Verify acceptance criterion 1 — no `sub_agents=` in orchestrator**

Run: `cd /mnt/c/Dev/GClaw && grep -n "sub_agents=" src/gclaw/agents/orchestrator.py`
Expected: no matches (exit code 1 from grep is fine and expected).

- [ ] **Step 3: Verify acceptance criterion 2 — RemoteRunner fully removed**

Run: `cd /mnt/c/Dev/GClaw && grep -rn "RemoteRunner\|remote_runner" src/ tests/`
Expected: no matches. Plan and spec documentation files are allowed to reference it (as history).

- [ ] **Step 4: Verify acceptance criterion 3 — all five manager configs exist**

Run: `cd /mnt/c/Dev/GClaw && ls agents/*.md soul/*.md`
Expected output includes: `agents/orchestrator.md`, `agents/workspace-mgr.md`, `agents/dev-mgr.md`, `agents/home-mgr.md`, `agents/comms-mgr.md`, `agents/research-mgr.md`, `soul/base.md`, `soul/workspace.md`, `soul/dev.md`, `soul/home.md`, `soul/comms.md`, `soul/research.md`.

- [ ] **Step 5: Verify acceptance criteria 4–6 — key integration tests pass**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/test_orchestrator_agenttool.py tests/test_integration_litellm_providers.py tests/test_workflows_morning_brief.py tests/test_workflows_commit_message.py -v`
Expected: PASS for all four files.

- [ ] **Step 6: Build the Docker image**

Run: `cd /mnt/c/Dev/GClaw && docker build -t gclaw:orchestration-refactor .`
Expected: build succeeds. If `gws` URL is wrong, the build fails at the curl step — fix the URL from the actual release asset name and rebuild.

Optional: if Docker isn't available in the environment, skip this step and note it — the CI pipeline will verify.

- [ ] **Step 7: Smoke test `gws` and `gh` are on PATH in the image**

Run (only if Step 6 succeeded):
```bash
docker run --rm --entrypoint sh gclaw:orchestration-refactor -c "which gws && which gh && gh --version"
```
Expected: prints paths for both binaries and a `gh` version.

- [ ] **Step 8: Final commit if any docs were touched**

If nothing changed in this task, no commit. Otherwise:

```bash
git add -u
git commit -m "chore: final acceptance check for orchestration refactor"
```

---

## Summary

| Task | What it builds | Green after |
|------|---------------|-------------|
| 1 | Pull `google-adk[extensions]` (LiteLlm) | Import check |
| 2 | Router `build_adk_model_for_{profile,agent}` | Unit tests |
| 3 | Factory `output_key` + ADK-ready model resolution | Unit tests |
| 4 | `tools/gws.py` subprocess helper | Unit tests |
| 5 | `tools/gh.py` subprocess helper | Unit tests |
| 6 | `tools/workspace_tools.py` (6 functions) | Unit tests |
| 7 | `tools/dev_tools.py` (6 functions) | Unit tests |
| 8 | `tools/{comms,research,home}_tools.py` | Unit tests |
| 9 | `workflows/validators.py` (`ValidateCommitMsg`) | Unit tests |
| 10 | `workflows/morning_brief.py` (ParallelAgent+SequentialAgent) | Unit tests |
| 11 | `workflows/commit_message.py` (SequentialAgent+Reviewer+Validate) | Unit tests |
| 12 | Scaffold home/comms/research agent + soul files | Files exist |
| 13 | Orchestrator rewrite (AgentTool delegation) | Smoke test |
| 14 | Orchestrator integration test (receptionist regression guard) | Integration test |
| 15 | Retire `RemoteRunner`, simplify dispatch, clean `ModelEndpoint` | Regression tests |
| 16 | LiteLlm provider integration test | Integration test |
| 17 | Dockerfile + `.env.example` + settings for `gws` | Build + env check |
| 18 | Full regression + acceptance criteria check | All 8 acceptance criteria met |

**Dependencies between tasks:**
- Tasks 1-4 are independent (router, factory, gws helper can run in parallel after Task 1).
- Task 5 (gh helper) is independent of everything except Task 1.
- Task 6 depends on Task 4.
- Task 7 depends on Task 5.
- Task 8 depends on Task 4 (for comms_tools).
- Task 9 is independent.
- Task 10 is independent (uses dummy tools in tests).
- Task 11 depends on Tasks 2, 9 (ModelRouter + ValidateCommitMsg).
- Task 12 is independent.
- Task 13 depends on Tasks 3, 6, 7, 8, 10, 11, 12 (everything for the orchestrator).
- Task 14 depends on Task 13.
- Task 15 depends on nothing except the existing codebase (could even run before Task 13, but it's placed here so the RemoteRunner deletion doesn't collide with the orchestrator rewrite that still references the old dispatch shape).
- Task 16 depends on Tasks 13, 15.
- Task 17 is independent.
- Task 18 depends on everything.
