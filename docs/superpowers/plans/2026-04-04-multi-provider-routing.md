# Multi-Provider Routing: Free-Tier APIs Implementation Plan

> **Status (2026-04-11): COMPLETE with architectural pivot.**
>
> All 7 tasks landed on `feat/multi-model-routing`, then Tasks 1 (partial), 3, and 4
> were deliberately reverted in `9c07595 refactor: retire RemoteRunner and simplify
> dispatch to a single ADK path`. The final architecture uses ADK's built-in
> `LiteLlm` adapter to wrap non-Gemini providers instead of the bespoke
> `RemoteRunner` class this plan specified. The dispatch layer now has a single
> path — ADK `Runner` for everything — because `LiteLlm` makes OpenRouter
> look like any other ADK model. See **Outcome** section at the bottom for the
> final shape. The task bodies below are preserved as historical record; do not
> re-execute them.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace self-hosted GPU endpoints with pay-per-token (and free-tier) API providers — Gemma 4 via Gemini API (free), Nemotron via OpenRouter (free), keeping total cost under $50/mo.

**Architecture (original — superseded):** Gemma 4 runs natively through ADK (same Gemini API, model string swap). Nemotron needs a `RemoteRunner` that calls OpenRouter's OpenAI-compatible API for text-generation tasks. The `ModelEndpoint` gains provider details (api_base, api_key_env) so the dispatch layer knows which execution path to use. Fallback to Gemini Flash when free tiers are exhausted (HTTP 429).

**Tech Stack:** Python 3.12, google-adk, openai SDK (for OpenRouter), FastAPI, Pydantic, pytest

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `src/gclaw/models/model_config.py` | Add api_base, api_key_env to ModelEndpoint |
| Modify | `src/gclaw/settings.py` | Add openrouter_api_key setting |
| Create | `src/gclaw/dispatch/remote_runner.py` | OpenAI-compatible runner for non-ADK models |
| Modify | `src/gclaw/dispatch/runner.py` | Dispatch to RemoteRunner when provider != "gemini" |
| Modify | `src/gclaw/main.py` | Wire Gemma 4 model ID + OpenRouter provider |
| Modify | `pyproject.toml` | Add openai as optional dependency |
| Modify | `.env.example` | Add OPENROUTER_API_KEY |
| Create | `tests/test_remote_runner.py` | RemoteRunner unit tests |
| Modify | `tests/test_model_config.py` | Tests for new endpoint fields |
| Modify | `tests/test_model_router.py` | Tests for provider-aware resolution |
| Create | `tests/test_integration_providers.py` | End-to-end provider routing test |

---

### Task 1: Extend ModelEndpoint with Provider Details

> **Status: PARTIALLY REVERTED.** Landed in `5b9f50c`. The `provider` field is retained,
> but `api_base`, `api_key_env`, and `is_remote` were stripped in `9c07595` — the
> LiteLlm-based architecture doesn't need them. Current `ModelEndpoint` has only
> `name`, `endpoint_id`, `provider`, `max_context_tokens`.

**Files:**
- Modify: `src/gclaw/models/model_config.py`
- Modify: `tests/test_model_config.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_model_config.py`:

```python
def test_model_endpoint_with_api_base():
    ep = ModelEndpoint(
        name="nemotron-3-super",
        endpoint_id="nvidia/nemotron-3-super-120b-a12b:free",
        provider="openrouter",
        api_base="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        max_context_tokens=1_000_000,
    )
    assert ep.api_base == "https://openrouter.ai/api/v1"
    assert ep.api_key_env == "OPENROUTER_API_KEY"
    assert ep.provider == "openrouter"


def test_model_endpoint_gemini_api_defaults():
    ep = ModelEndpoint(
        name="gemma-4-26b",
        endpoint_id="gemma-4-26b-it",
        provider="gemini",
    )
    assert ep.api_base is None
    assert ep.api_key_env is None


def test_model_endpoint_is_remote():
    remote = ModelEndpoint(
        name="nemotron",
        endpoint_id="nvidia/nemotron-3-super-120b-a12b:free",
        provider="openrouter",
        api_base="https://openrouter.ai/api/v1",
    )
    local = ModelEndpoint(
        name="gemma",
        endpoint_id="gemma-4-26b-it",
        provider="gemini",
    )
    assert remote.is_remote is True
    assert local.is_remote is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/test_model_config.py -v`
Expected: FAIL — `api_base`, `api_key_env`, `is_remote` don't exist

- [ ] **Step 3: Update ModelEndpoint**

Replace `src/gclaw/models/model_config.py`:

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
    """A model endpoint — Gemini API, OpenRouter, or self-hosted."""

    name: str
    endpoint_id: str
    provider: str = "gemini"
    api_base: str | None = None
    api_key_env: str | None = None
    max_context_tokens: int = 0

    @property
    def is_remote(self) -> bool:
        """True if this endpoint uses a non-Gemini API (needs RemoteRunner)."""
        return self.provider not in ("gemini", "vertex")


class RoutingRule(BaseModel):
    """Maps a task profile to a model name."""

    task_profile: TaskProfile
    model_name: str
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/test_model_config.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/gclaw/models/model_config.py tests/test_model_config.py
git commit -m "feat: extend ModelEndpoint with api_base, api_key_env, and is_remote"
```

---

### Task 2: Settings — OpenRouter API Key

> **Status: DONE and retained.** `OPENROUTER_API_KEY` is read by
> `Settings.openrouter_api_key` and consumed in `main.py` when building the
> Nemotron endpoint.

**Files:**
- Modify: `src/gclaw/settings.py`
- Modify: `tests/test_settings_models.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_settings_models.py`:

```python
def test_settings_openrouter_api_key_default():
    os.environ["GCP_PROJECT_ID"] = "test-project"
    s = Settings()
    assert s.openrouter_api_key == ""


def test_settings_openrouter_api_key_set():
    os.environ["GCP_PROJECT_ID"] = "test-project"
    os.environ["OPENROUTER_API_KEY"] = "sk-or-test-123"
    try:
        s = Settings()
        assert s.openrouter_api_key == "sk-or-test-123"
    finally:
        os.environ.pop("OPENROUTER_API_KEY", None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/test_settings_models.py -v`
Expected: FAIL — `openrouter_api_key` doesn't exist

- [ ] **Step 3: Add the setting**

Add after `nemotron_provider` field in `src/gclaw/settings.py`:

```python
    openrouter_api_key: str = field(
        default_factory=lambda: os.environ.get("OPENROUTER_API_KEY", "")
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/test_settings_models.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/gclaw/settings.py tests/test_settings_models.py
git commit -m "feat: add OPENROUTER_API_KEY setting"
```

---

### Task 3: RemoteRunner — OpenAI-Compatible Execution

> **Status: REVERTED.** Built in `d5facda`, removed in `9c07595`. Neither
> `src/gclaw/dispatch/remote_runner.py` nor `tests/test_remote_runner.py` exists.
> Reason: ADK's `LiteLlm` adapter already wraps OpenAI-compatible providers as
> native ADK models, so the bespoke runner was duplicate infrastructure. The
> router now wraps non-Gemini endpoints with `LiteLlm` at model-build time
> (`build_adk_model_for_profile`) and everything flows through ADK's `Runner`.

**Files:**
- Create: `src/gclaw/dispatch/remote_runner.py`
- Create: `tests/test_remote_runner.py`

This is the core new component. It calls OpenRouter (or any OpenAI-compatible API) for agents that use non-Gemini models.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_remote_runner.py
"""Tests for RemoteRunner (OpenAI-compatible API client)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from gclaw.dispatch.remote_runner import RemoteRunner


def test_remote_runner_init():
    runner = RemoteRunner(
        model="nvidia/nemotron-3-super-120b-a12b:free",
        api_base="https://openrouter.ai/api/v1",
        api_key="sk-or-test-123",
    )
    assert runner._model == "nvidia/nemotron-3-super-120b-a12b:free"
    assert runner._api_base == "https://openrouter.ai/api/v1"


@pytest.mark.asyncio
async def test_remote_runner_generate():
    runner = RemoteRunner(
        model="nvidia/nemotron-3-super-120b-a12b:free",
        api_base="https://openrouter.ai/api/v1",
        api_key="sk-or-test-123",
    )

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "The answer is 42."

    with patch.object(runner, "_client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        result = await runner.generate(
            system_prompt="You are helpful.",
            message="What is the answer?",
        )

    assert result == "The answer is 42."


@pytest.mark.asyncio
async def test_remote_runner_generate_with_history():
    runner = RemoteRunner(
        model="nvidia/nemotron-3-super-120b-a12b:free",
        api_base="https://openrouter.ai/api/v1",
        api_key="sk-or-test-123",
    )

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Follow-up answer."

    with patch.object(runner, "_client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        result = await runner.generate(
            system_prompt="You are helpful.",
            message="Follow-up question.",
            history=[
                {"role": "user", "content": "First question."},
                {"role": "assistant", "content": "First answer."},
            ],
        )

    assert result == "Follow-up answer."
    # Verify history was included in the call
    call_args = mock_client.chat.completions.create.call_args
    messages = call_args.kwargs["messages"]
    assert len(messages) == 4  # system + 2 history + user


@pytest.mark.asyncio
async def test_remote_runner_handles_rate_limit():
    runner = RemoteRunner(
        model="nvidia/nemotron-3-super-120b-a12b:free",
        api_base="https://openrouter.ai/api/v1",
        api_key="sk-or-test-123",
    )

    from openai import RateLimitError

    with patch.object(runner, "_client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(
            side_effect=RateLimitError(
                message="Rate limit exceeded",
                response=MagicMock(status_code=429),
                body=None,
            )
        )
        with pytest.raises(RateLimitError):
            await runner.generate(
                system_prompt="You are helpful.",
                message="Hello",
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/test_remote_runner.py -v`
Expected: FAIL — module doesn't exist

- [ ] **Step 3: Add openai dependency**

In `pyproject.toml`, add `"openai>=1.0.0"` to the dependencies list:

```toml
dependencies = [
    "google-adk>=1.0.0",
    "google-cloud-firestore>=2.19.0",
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.34.0",
    "pydantic>=2.10.0",
    "python-dotenv>=1.0.0",
    "firebase-admin>=6.4.0",
    "openai>=1.0.0",
]
```

Then install: `pip install -e ".[dev]"`

- [ ] **Step 4: Write the RemoteRunner**

```python
# src/gclaw/dispatch/remote_runner.py
"""Run agent turns via OpenAI-compatible APIs (OpenRouter, NVIDIA API, etc.)."""

from __future__ import annotations

import logging

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class RemoteRunner:
    """Calls an OpenAI-compatible API for text generation.

    Used for non-Gemini models (Nemotron via OpenRouter, etc.) that
    can't run through ADK's native Runner. Supports system prompts,
    multi-turn history, and rate limit propagation.
    """

    def __init__(
        self,
        model: str,
        api_base: str,
        api_key: str,
    ) -> None:
        self._model = model
        self._api_base = api_base
        self._client = AsyncOpenAI(
            base_url=api_base,
            api_key=api_key,
        )

    async def generate(
        self,
        system_prompt: str,
        message: str,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        """Generate a response from the remote model.

        Args:
            system_prompt: The agent's system instruction.
            message: The current user message.
            history: Optional list of prior messages as
                     [{"role": "user"|"assistant", "content": "..."}].

        Returns:
            The model's text response.

        Raises:
            openai.RateLimitError: If the provider returns HTTP 429.
        """
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
        ]

        if history:
            messages.extend(history)

        messages.append({"role": "user", "content": message})

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
        )

        return response.choices[0].message.content
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/test_remote_runner.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add src/gclaw/dispatch/remote_runner.py tests/test_remote_runner.py pyproject.toml
git commit -m "feat: add RemoteRunner for OpenAI-compatible APIs (OpenRouter, NVIDIA)"
```

---

### Task 4: AgentRunner — Provider-Aware Dispatch

> **Status: REVERTED.** Landed in `a17bb2c`, removed in `9c07595`. `AgentRunner`
> no longer has a `remote_runner` parameter or a `_run_remote` branch — there is
> exactly one execution path through ADK's `Runner`.

**Files:**
- Modify: `src/gclaw/dispatch/runner.py`
- Modify: `tests/test_dispatcher.py`

The AgentRunner gains an optional `remote_runner` for non-ADK models. When a remote runner is present, it uses that instead of ADK's Runner.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_dispatcher.py`:

```python
from gclaw.dispatch.remote_runner import RemoteRunner


@pytest.mark.asyncio
async def test_runner_with_remote_runner():
    agent = MagicMock()
    agent.name = "code_specialist"
    agent.instruction = "You write code."
    session_service = AsyncMock()

    remote = AsyncMock(spec=RemoteRunner)
    remote.generate = AsyncMock(return_value="def hello(): pass")

    runner = AgentRunner(
        agent=agent,
        app_name="gclaw",
        session_service=session_service,
        remote_runner=remote,
    )

    response = await runner.run(
        user_id="user_1",
        session_id="session_123",
        message="Write a hello function",
    )

    assert response.text == "def hello(): pass"
    remote.generate.assert_called_once()


@pytest.mark.asyncio
async def test_runner_remote_runner_none_uses_adk():
    """When remote_runner is None, uses ADK Runner (existing behavior)."""
    agent = MagicMock()
    agent.name = "orchestrator"
    session_service = AsyncMock()

    runner = AgentRunner(
        agent=agent,
        app_name="gclaw",
        session_service=session_service,
        remote_runner=None,
    )

    # Verify it uses ADK runner (no remote_runner set)
    assert runner._remote_runner is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/test_dispatcher.py -v`
Expected: FAIL — `remote_runner` param doesn't exist

- [ ] **Step 3: Update AgentRunner**

Replace `src/gclaw/dispatch/runner.py`:

```python
"""Run agent turns via ADK Runner or RemoteRunner."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService
from google.genai import types

if TYPE_CHECKING:
    from gclaw.dispatch.remote_runner import RemoteRunner
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

    When a RemoteRunner is provided, uses it instead of ADK Runner.
    This enables non-Gemini models (Nemotron via OpenRouter, etc.)
    that can't run through ADK natively.

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
        remote_runner: RemoteRunner | None = None,
    ) -> None:
        self._agent = agent
        self._app_name = app_name
        self._session_service = session_service
        self._memory_service = memory_service
        self._remote_runner = remote_runner
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
        2. Execute the agent turn (ADK or remote)
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

        # 2. Execute via remote runner or ADK
        if self._remote_runner is not None:
            response = await self._run_remote(full_message)
        else:
            response = await self._run_adk(user_id, session_id, full_message)

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

    async def _run_remote(self, message: str) -> AgentResponse:
        """Execute via RemoteRunner (OpenAI-compatible API)."""
        text = await self._remote_runner.generate(
            system_prompt=self._agent.instruction,
            message=message,
        )
        return AgentResponse(text=text, is_final=True)

    async def _run_adk(
        self,
        user_id: str,
        session_id: str,
        full_message: str,
    ) -> AgentResponse:
        """Execute via ADK Runner (Gemini/Gemma models)."""
        # Ensure session exists (auto-create if not found)
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
                pass  # Session already exists

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

        return response
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/test_dispatcher.py -v`
Expected: PASS (all tests including new ones)

- [ ] **Step 5: Run full test suite to check regressions**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/ --tb=short -q`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/gclaw/dispatch/runner.py tests/test_dispatcher.py
git commit -m "feat: add provider-aware dispatch — remote runner for non-ADK models"
```

---

### Task 5: Wire Free-Tier Providers into main.py

> **Status: DONE, evolved.** The `_build_model_router` function in `main.py`
> registers Gemini Flash, Gemma 4, and Nemotron 3 Super exactly as specified,
> but without the `api_base` / `api_key_env` fields (removed in the LiteLlm
> pivot). The OpenRouter API surface is now handled by `LiteLlm` wrapping inside
> `src/gclaw/routing/router.py::build_adk_model_for_profile`, not at endpoint
> registration.

**Files:**
- Modify: `src/gclaw/main.py`

Replace `_build_model_router` to use Gemma 4 via Gemini API (model string) and Nemotron via OpenRouter. No more self-hosted endpoint IDs.

- [ ] **Step 1: Update _build_model_router in main.py**

Replace the `_build_model_router` function in `src/gclaw/main.py`:

```python
def _build_model_router(settings):
    """Build a ModelRouter from settings, or return None if disabled."""
    if not settings.model_routing_enabled:
        return None

    from gclaw.models.model_config import ModelEndpoint, TaskProfile, RoutingRule
    from gclaw.routing.router import ModelRouter

    endpoints: dict[str, ModelEndpoint] = {}
    rules: list[RoutingRule] = []

    # Gemini Flash — free tier default, always available
    endpoints["gemini-flash"] = ModelEndpoint(
        name="gemini-flash",
        endpoint_id=settings.gemini_flash_model,
        provider="gemini",
        max_context_tokens=1_000_000,
    )

    # Orchestrator uses Gemini Flash (free) — good enough for routing
    rules.append(RoutingRule(task_profile=TaskProfile.ORCHESTRATION, model_name="gemini-flash"))
    rules.append(RoutingRule(task_profile=TaskProfile.PERSONALITY, model_name="gemini-flash"))

    # Gemma 4 via Gemini API — free, same API surface
    if settings.gemma_endpoint_id:
        endpoints["gemma-4"] = ModelEndpoint(
            name="gemma-4",
            endpoint_id=settings.gemma_endpoint_id,
            provider="gemini",
            max_context_tokens=256_000,
        )
        rules.extend([
            RoutingRule(task_profile=TaskProfile.SUMMARIZATION, model_name="gemma-4"),
            RoutingRule(task_profile=TaskProfile.BACKGROUND, model_name="gemma-4"),
        ])
        logger.info("Gemma 4 registered (Gemini API): %s", settings.gemma_endpoint_id)

    # Nemotron via OpenRouter — free tier
    if settings.nemotron_endpoint_id and settings.openrouter_api_key:
        endpoints["nemotron-3-super"] = ModelEndpoint(
            name="nemotron-3-super",
            endpoint_id=settings.nemotron_endpoint_id,
            provider="openrouter",
            api_base="https://openrouter.ai/api/v1",
            api_key_env="OPENROUTER_API_KEY",
            max_context_tokens=1_000_000,
        )
        rules.extend([
            RoutingRule(task_profile=TaskProfile.TOOL_EXECUTION, model_name="nemotron-3-super"),
            RoutingRule(task_profile=TaskProfile.CODE_GENERATION, model_name="nemotron-3-super"),
        ])
        logger.info("Nemotron 3 Super registered (OpenRouter): %s", settings.nemotron_endpoint_id)

    return ModelRouter(
        endpoints=endpoints,
        rules=rules,
        default_model=settings.gemini_flash_model,
    )
```

- [ ] **Step 2: Commit**

```bash
git add src/gclaw/main.py
git commit -m "feat: wire Gemma 4 (Gemini API) and Nemotron (OpenRouter) as free-tier providers"
```

---

### Task 6: Update .env.example and Deploy Scripts

> **Status: DONE.** `.env.example` lists `MODEL_ROUTING_ENABLED`,
> `GEMMA_ENDPOINT_ID`, `NEMOTRON_ENDPOINT_ID`, `NEMOTRON_PROVIDER`, and
> `OPENROUTER_API_KEY`.

**Files:**
- Modify: `.env.example`
- Modify: `infra/vertex-models/README.md`

- [ ] **Step 1: Update .env.example**

Replace the model routing section in `.env.example`:

```bash
# === Model Routing (optional) ===
MODEL_ROUTING_ENABLED=false

# Gemma 4 26B MoE via Gemini API (free tier)
# Model ID served through same API as Gemini — no GPU endpoint needed
GEMMA_ENDPOINT_ID=gemma-4-26b-it

# Nemotron 3 Super via OpenRouter (free tier)
# Sign up at https://openrouter.ai for an API key
NEMOTRON_ENDPOINT_ID=nvidia/nemotron-3-super-120b-a12b:free
NEMOTRON_PROVIDER=openrouter
OPENROUTER_API_KEY=
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: update .env.example for free-tier API providers"
```

---

### Task 7: Integration Test — Full Provider Pipeline

> **Status: DONE (renamed).** Landed as
> `tests/test_integration_litellm_providers.py` (not
> `test_integration_providers.py`) — the LiteLlm variant. An additional
> `tests/test_integration_routing.py` covers the end-to-end routing path.

**Files:**
- Create: `tests/test_integration_providers.py`

- [ ] **Step 1: Write the integration test**

```python
# tests/test_integration_providers.py
"""Integration test: multi-provider routing with Gemini, Gemma, and OpenRouter."""

import pytest
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
def free_tier_router():
    """Router configured for free-tier APIs only."""
    endpoints = {
        "gemini-flash": ModelEndpoint(
            name="gemini-flash",
            endpoint_id="gemini-2.5-flash",
            provider="gemini",
            max_context_tokens=1_000_000,
        ),
        "gemma-4": ModelEndpoint(
            name="gemma-4",
            endpoint_id="gemma-4-26b-it",
            provider="gemini",
            max_context_tokens=256_000,
        ),
        "nemotron-3-super": ModelEndpoint(
            name="nemotron-3-super",
            endpoint_id="nvidia/nemotron-3-super-120b-a12b:free",
            provider="openrouter",
            api_base="https://openrouter.ai/api/v1",
            api_key_env="OPENROUTER_API_KEY",
            max_context_tokens=1_000_000,
        ),
    }
    rules = [
        RoutingRule(task_profile=TaskProfile.ORCHESTRATION, model_name="gemini-flash"),
        RoutingRule(task_profile=TaskProfile.PERSONALITY, model_name="gemini-flash"),
        RoutingRule(task_profile=TaskProfile.SUMMARIZATION, model_name="gemma-4"),
        RoutingRule(task_profile=TaskProfile.BACKGROUND, model_name="gemma-4"),
        RoutingRule(task_profile=TaskProfile.TOOL_EXECUTION, model_name="nemotron-3-super"),
        RoutingRule(task_profile=TaskProfile.CODE_GENERATION, model_name="nemotron-3-super"),
    ]
    return ModelRouter(endpoints=endpoints, rules=rules, default_model="gemini-2.5-flash")


def test_orchestrator_uses_gemini_flash(config_dir, free_tier_router):
    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(loader=loader, default_model="gemini-2.5-flash", model_router=free_tier_router)
    agent = factory.build(agent_name="orchestrator")
    assert agent.model == "gemini-2.5-flash"


def test_workspace_mgr_uses_gemma_4(config_dir, free_tier_router):
    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(loader=loader, default_model="gemini-2.5-flash", model_router=free_tier_router)
    agent = factory.build(agent_name="workspace-mgr", soul_overlay="workspace")
    assert agent.model == "gemma-4-26b-it"


def test_dev_mgr_uses_nemotron(config_dir, free_tier_router):
    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(loader=loader, default_model="gemini-2.5-flash", model_router=free_tier_router)
    agent = factory.build(agent_name="dev-mgr", soul_overlay="dev")
    assert agent.model == "nvidia/nemotron-3-super-120b-a12b:free"


def test_nemotron_endpoint_is_remote(free_tier_router):
    ep = free_tier_router.get_endpoint(TaskProfile.CODE_GENERATION)
    assert ep is not None
    assert ep.is_remote is True
    assert ep.api_base == "https://openrouter.ai/api/v1"


def test_gemma_endpoint_is_not_remote(free_tier_router):
    ep = free_tier_router.get_endpoint(TaskProfile.SUMMARIZATION)
    assert ep is not None
    assert ep.is_remote is False


def test_all_providers_accounted_for(free_tier_router):
    """Every task profile resolves to a model."""
    for profile in TaskProfile:
        model_id = free_tier_router.resolve(profile)
        assert model_id is not None
        assert model_id != ""
```

- [ ] **Step 2: Run tests**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/test_integration_providers.py -v`
Expected: PASS (6 tests)

- [ ] **Step 3: Run full test suite**

Run: `cd /mnt/c/Dev/GClaw && python3 -m pytest tests/ --tb=short -q`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration_providers.py
git commit -m "test: add integration tests for free-tier multi-provider routing"
```

---

## Summary (original intent)

| Task | What it builds | Cost impact |
|------|---------------|-------------|
| 1 | ModelEndpoint gains api_base, api_key_env, is_remote | Enables multi-provider |
| 2 | OPENROUTER_API_KEY setting | Auth for OpenRouter |
| 3 | RemoteRunner (OpenAI-compatible client) | Nemotron execution path |
| 4 | AgentRunner provider-aware dispatch | Routes to ADK or RemoteRunner |
| 5 | main.py wiring for free-tier APIs | Gemma=free, Nemotron=free |
| 6 | .env.example update | Documentation |
| 7 | Integration tests | Validation |

**Before:** Self-hosted GPUs, ~$1,300+/mo
**After:** Free-tier APIs, ~$0-30/mo

---

## Outcome (what actually shipped)

The branch `feat/multi-model-routing` implemented the plan through task 7, then
pivoted in `9c07595 refactor: retire RemoteRunner and simplify dispatch to a
single ADK path`. The final architecture replaces the bespoke `RemoteRunner`
with ADK's `LiteLlm` adapter, giving a single dispatch path.

**What was kept:**
- `ModelEndpoint.provider` field (task 1, minus `api_base`/`api_key_env`/`is_remote`)
- `Settings.openrouter_api_key` (task 2)
- `main.py::_build_model_router` with Gemini Flash / Gemma 4 / Nemotron 3 Super registration (task 5)
- `.env.example` variables (task 6)
- `tests/test_integration_litellm_providers.py` + `tests/test_integration_routing.py` (task 7, renamed)

**What was removed:**
- `src/gclaw/dispatch/remote_runner.py` (task 3)
- `AgentRunner.remote_runner` parameter and `_run_remote` branch (task 4)
- `ModelEndpoint.api_base` / `api_key_env` / `is_remote` (task 1 partial revert)
- `tests/test_remote_runner.py`

**Key file added after the pivot:**
- `src/gclaw/routing/router.py::build_adk_model_for_profile` /
  `build_adk_model_for_agent` (commit `b3b0423`) — wraps non-Gemini endpoints
  with `LiteLlm` at model-build time so ADK's `Runner` can execute them
  natively.

**Final routing:**
```
Orchestrator     → Gemini Flash (free)   — via ADK
Managers         → Gemma 4 26B (free)    — via ADK (same Gemini API)
Code specialists → Nemotron Super (free) — via ADK with LiteLlm(OpenRouter)
Fallback         → Gemini Flash (free)   — via ADK
```

**Lesson for next plan:** Check whether ADK's `LiteLlm` (or the platform SDK's
equivalent adapter) already covers the "non-native provider" case before
speccing a bespoke runner. The plan was written against an incorrect mental
model of ADK's capabilities, and the revert was the right call.
