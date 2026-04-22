---
title: Orchestration Refactor — AgentTool, Composed Workflows, LiteLlm Unification
date: 2026-04-10
status: approved
author: maintainer (brainstormed with Claude)
supersedes_parts_of: docs/superpowers/plans/2026-04-04-multi-provider-routing.md
---

# Orchestration Refactor

## Goal

Replace GClaw's current `LlmAgent(sub_agents=[...])` routing pattern — which the Google ADK team calls "a great receptionist but a poor project manager" — with Google ADK's native multi-agent patterns: `AgentTool` for delegation, `ParallelAgent` + `SequentialAgent` for composition, and Reviewer/Validate agents for self-regulating quality gates.

Unify all non-Gemini providers under ADK's `LiteLlm` wrapper so every agent runs on one execution path, and retire the bespoke `RemoteRunner` that was built a week ago as a side channel.

Scaffold all five manager tiers (workspace, dev, home, comms, research) as thin routers bound to real subprocess-backed domain tools (`gws` for Google Workspace, `gh` for GitHub) where available, with stubs for the rest.

## Non-Goals

- **Memory layer upgrade.** The always-on memory agent (ingest/consolidate/query) is the next spec, tackled after this refactor lands.
- **Skill design patterns.** Formalizing the five skill patterns (Tool Wrapper, Generator, Reviewer, Inversion, Pipeline) is the third spec.
- **Full Home/Comms/Research tool integrations.** This spec stubs tools that don't map cleanly to `gws`/`gh`; real integrations come later.
- **Three-tier specialist hierarchy under managers.** Managers stay flat routers — dynamic specialist spawning is a future concern. "Workflow specialists" exist only as private sub-agents inside composed workflows, not as persistent agents under managers.
- **Board schema changes.** Board remains a FIFO task queue with an `assignee` field that names a manager.

## Architecture

### Entry-point rules

| Source | Target | Notes |
|---|---|---|
| User turn (web/voice/mobile) | **Orchestrator** | Always. Classifies intent, picks a tool (manager / workflow / board op). |
| Cron — single-step | **Manager directly** | Deterministic work. Cron knows the target. Bypasses intent classification. |
| Cron — multi-step workflow | **Orchestrator** | Cron sends a prompt like "give me my morning brief"; orchestrator routes to the workflow tool. |
| Board worker | **Manager directly** | Task `assignee` names the target. Worker constructs prompt from description. |

**Constraint:** workflow specialists (`workspace_brief_specialist`, `commit_draft_specialist`, etc.) are *private* to their workflow. Nothing targets them directly.

### Hierarchy

```
Orchestrator (router, Gemini Flash)
  │
  │  tools = [
  │    AgentTool(workspace_mgr),
  │    AgentTool(dev_mgr),
  │    AgentTool(home_mgr),
  │    AgentTool(comms_mgr),
  │    AgentTool(research_mgr),
  │    AgentTool(morning_brief_workflow),
  │    AgentTool(commit_message_workflow),
  │    create_board_task,
  │    list_board_tasks,
  │    get_board_task,
  │    complete_board_task,
  │  ]
  │
  ├── workspace_mgr  (router, Gemma-4)   tools=[gws helpers: gmail, calendar, drive, docs]
  ├── dev_mgr        (router, Nemotron via LiteLlm)   tools=[gh helpers: prs, issues, diff; local: read_file, run_tests]
  ├── home_mgr       (router, Gemma-4)   tools=[stub: list_devices, set_device_state]
  ├── comms_mgr      (router, Gemma-4)   tools=[gws chat: list_spaces, post_message]
  ├── research_mgr   (router, Gemma-4)   tools=[stub: web_search; real: fetch_url]
  │
  ├── morning_brief_workflow  (SequentialAgent)
  │     ├── ParallelAgent(
  │     │     workspace_brief_specialist   (LlmAgent, output_key="workspace_summary")
  │     │     dev_brief_specialist         (LlmAgent, output_key="dev_summary")
  │     │     research_brief_specialist    (LlmAgent, output_key="research_summary")
  │     │   )
  │     └── brief_summary_agent            (LlmAgent, output_key="morning_brief")
  │
  └── commit_message_workflow  (SequentialAgent)
        ├── commit_draft_specialist   (LlmAgent via LiteLlm/Nemotron, output_key="commit_draft")
        ├── style_reviewer_specialist (LlmAgent, output_key="review_status")
        └── ValidateCommitMsg         (custom BaseAgent, reads state, yields final Event)
```

**Key property:** managers and workflow specialists share **the same tool functions**. `gmail_list_unread` is a plain Python callable bound to both `workspace_mgr` (as one of its routing choices) and `workspace_brief_specialist` (as the function it uses to gather brief data). Tool logic is never duplicated.

### Execution model

- **`AgentRunner` remains the outer wrapper.** One entry point per turn. Auto-recall once at start, auto-capture once at end. No per-AgentTool memory hooks. Memory scope is the user, not the specific sub-agent.
- **`AgentRunner.agent` becomes polymorphic.** It can hold either the orchestrator (user/multi-step-cron turns) or a specific manager (single-step-cron/board-worker turns). Same memory hooks fire regardless. Tests verify both entry shapes.
- **`RemoteRunner` is deleted.** All non-Gemini providers route through `LiteLlm`, which ADK's native `Runner` executes. One code path, no conditional dispatch.

## File Map

### Created

| File | Purpose |
|---|---|
| `src/gclaw/tools/__init__.py` | Already exists, stays. |
| `src/gclaw/tools/gws.py` | Helper `run_gws(*args) -> dict` — async subprocess wrapper around `gws`, parses JSON stdout, raises on non-zero exit. |
| `src/gclaw/tools/gh.py` | Helper `run_gh(*args) -> dict` — same pattern for `gh` CLI. |
| `src/gclaw/tools/workspace_tools.py` | Thin tool functions: `list_unread_email`, `send_email`, `list_calendar_events_today`, `create_calendar_event`, `list_drive_files`, `read_drive_doc`. Each ~10 lines calling `run_gws`. |
| `src/gclaw/tools/dev_tools.py` | Thin tool functions: `list_open_prs`, `get_pr_diff`, `list_failing_workflows`, `create_issue`, `get_current_diff` (local `git diff`), `read_local_file`. |
| `src/gclaw/tools/comms_tools.py` | `list_chat_spaces`, `post_chat_message` via `run_gws chat ...`. |
| `src/gclaw/tools/research_tools.py` | `web_search` (stub returning placeholder text + TODO comment), `fetch_url` (real, using httpx). |
| `src/gclaw/tools/home_tools.py` | `list_devices`, `set_device_state` (both stubs). |
| `src/gclaw/agents/workflows/__init__.py` | Empty package marker. |
| `src/gclaw/agents/workflows/morning_brief.py` | `build_morning_brief(factory, tools) -> SequentialAgent`. Constructs three brief specialists + a summary agent, wraps in ParallelAgent then SequentialAgent. |
| `src/gclaw/agents/workflows/commit_message.py` | `build_commit_message_workflow(factory, tools) -> SequentialAgent`. Constructs draft specialist + reviewer + `ValidateCommitMsg` custom agent. |
| `src/gclaw/agents/workflows/validators.py` | `ValidateCommitMsg(BaseAgent)` — reads `review_status` and `commit_draft` from session state; yields pass Event (with the draft) or fail Event (with feedback). |
| `agents/home-mgr.md` | Thin router agent definition. |
| `agents/comms-mgr.md` | Thin router agent definition. |
| `agents/research-mgr.md` | Thin router agent definition. |
| `soul/home.md` | Personality overlay for home manager. |
| `soul/comms.md` | Personality overlay for comms manager. |
| `soul/research.md` | Personality overlay for research manager. |
| `tests/test_tools_gws.py` | Unit tests for `run_gws` — mocks subprocess, asserts arg construction and JSON parsing. |
| `tests/test_tools_gh.py` | Same pattern for `run_gh`. |
| `tests/test_workspace_tools.py` | Unit tests for each workspace tool function — mocks `run_gws`, asserts the call shape. |
| `tests/test_dev_tools.py` | Same for dev tools. |
| `tests/test_workflows_morning_brief.py` | Unit tests: asserts the SequentialAgent structure, that each sub-agent is called, and that session state keys propagate. |
| `tests/test_workflows_commit_message.py` | Unit tests: asserts pass-path and fail-path through `ValidateCommitMsg`. |
| `tests/test_orchestrator_agenttool.py` | Integration test: orchestrator with AgentTool-wrapped managers handles a multi-turn composed request. Uses a fake LLM that records tool invocations. |

### Modified

| File | Change |
|---|---|
| `pyproject.toml` | Add `google-adk[extensions]` to pull `litellm`. Keep `openai` dep (LiteLlm uses it internally). |
| `Dockerfile` | Add a `RUN` step to install `gws` binary — download latest release from GitHub rather than `npm install -g` (smaller image, no Node runtime). Pin version in a build arg. |
| `.env.example` | Add `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE=` (path to service account JSON). Remove nothing — `OPENROUTER_API_KEY` stays because LiteLlm reads it. |
| `src/gclaw/settings.py` | Add `google_workspace_credentials_file: str` setting. No removals. |
| `src/gclaw/routing/router.py` | Add two helpers: `build_adk_model_for_agent(agent_name: str) -> str \| LiteLlm` (used by the factory when building a named agent) and `build_adk_model_for_profile(profile: TaskProfile) -> str \| LiteLlm` (used directly by workflows that construct raw `LlmAgent` instances). Both resolve the endpoint; Gemini/Vertex providers return the string model ID, other providers return a `LiteLlm(model="openrouter/<id>")` instance. Router becomes the single place that knows provider→ADK-model mapping. Keep the existing `resolve_for_agent(name) -> str` for backward compatibility until callers migrate, then delete in task 6. |
| `src/gclaw/agents/factory.py` | `build()` signature adds `output_key: str \| None = None`. Model resolution calls `router.build_adk_model_for_agent(agent_name)` which returns either a string (Gemini) or a `LiteLlm` instance (non-Gemini). `LlmAgent(...)` construction passes the resolved model and `output_key=output_key`. |
| `src/gclaw/agents/orchestrator.py` | **Rewrite.** Remove `sub_agents=[...]`. Build all five managers via factory, wrap each with `agent_tool.AgentTool(agent=..., skip_summarization=False)`. Build the two composed workflows via `build_morning_brief` and `build_commit_message_workflow`; wrap each with `AgentTool`. Pass all AgentTools + the existing board function tools to the root orchestrator's `tools=[...]`. |
| `src/gclaw/dispatch/runner.py` | Delete `_run_remote`, `remote_runner` ctor param, `TYPE_CHECKING` import. `run()` only calls `_run_adk`. Memory hooks unchanged. Docstring updated. |
| `src/gclaw/main.py` | `_build_model_router` no longer sets `api_base`/`api_key_env` on `ModelEndpoint` — provider info suffices. `build_app()` passes `router=model_router` and `default_model=settings.gemini_flash_model` into `build_orchestrator`. |
| `src/gclaw/models/model_config.py` | Remove `api_base`, `api_key_env`, and `is_remote` — these existed only to support `RemoteRunner`. `ModelEndpoint` goes back to `{name, endpoint_id, provider, max_context_tokens}`. |
| `tests/test_dispatcher.py` | Remove the two `remote_runner` tests. Add a test that asserts `AgentRunner` can target either an orchestrator or a plain manager. |
| `tests/test_model_config.py` | Remove `test_model_endpoint_with_api_base`, `test_model_endpoint_is_remote`. |

### Deleted

| File | Reason |
|---|---|
| `src/gclaw/dispatch/remote_runner.py` | Replaced by LiteLlm. |
| `tests/test_remote_runner.py` | Module deleted. |
| `tests/test_integration_providers.py` | Current version asserts `is_remote` behavior on endpoints; rewrite-in-place as `test_integration_litellm_providers.py` that asserts the LiteLlm wrapping path instead. (Listed as deleted + created rather than modified because the assertions flip entirely.) |

## Detailed designs

### `router` LiteLlm helpers

```python
# src/gclaw/routing/router.py (additions)

from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from google.adk.models.lite_llm import LiteLlm

AdkModel = Union[str, "LiteLlm"]  # type alias


def _endpoint_to_adk_model(endpoint: ModelEndpoint | None, default: str) -> AdkModel:
    """Convert a ModelEndpoint to an ADK-ready model reference."""
    if endpoint is None:
        return default

    if endpoint.provider in ("gemini", "vertex"):
        return endpoint.endpoint_id

    # Non-Gemini providers: wrap with LiteLlm
    from google.adk.models.lite_llm import LiteLlm

    prefixed = endpoint.endpoint_id
    if endpoint.provider == "openrouter" and not prefixed.startswith("openrouter/"):
        prefixed = f"openrouter/{prefixed}"

    # LiteLlm reads OPENROUTER_API_KEY from env by convention; no extra wiring needed.
    return LiteLlm(model=prefixed)


# Methods on ModelRouter:

def build_adk_model_for_profile(self, profile: TaskProfile) -> AdkModel:
    """Return an ADK-ready model for a task profile (used by workflow specialists)."""
    endpoint = self.get_endpoint(profile)  # existing method
    return _endpoint_to_adk_model(endpoint, self._default)


def build_adk_model_for_agent(self, agent_name: str) -> AdkModel:
    """Return an ADK-ready model for a named agent (used by the factory)."""
    profile = AGENT_PROFILE_MAP.get(agent_name)
    if profile is None:
        # Fall back to suffix matching for dynamic specialists
        for suffix, prof in SPECIALIST_SUFFIX_MAP.items():
            if suffix in agent_name:
                profile = prof
                break
    if profile is None:
        return self._default
    return self.build_adk_model_for_profile(profile)
```

**No changes to `SPECIALIST_SUFFIX_MAP` needed in this spec.** The commit draft specialist is built as a raw `LlmAgent` with `model=router.build_adk_model_for_profile(TaskProfile.CODE_GENERATION)` — it doesn't round-trip through `build_adk_model_for_agent`, so the existing `"draft": TaskProfile.PERSONALITY` entry doesn't affect it. If we later add named draft specialists via the factory, revisit the suffix-map ordering then.

### `factory.build` signature change

```python
def build(
    self,
    agent_name: str,
    soul_overlay: str | None = None,
    memories: list[str] | None = None,
    tools: list[Any] | None = None,
    sub_agents: list[LlmAgent] | None = None,
    model: str | None = None,
    description: str | None = None,
    output_key: str | None = None,   # NEW
) -> LlmAgent:
    instruction = self._loader.build_system_prompt(...)

    # Model resolution: explicit > router (as ADK-ready object) > default string
    adk_model: str | object
    if model is not None:
        adk_model = model  # explicit override (string or pre-built LiteLlm)
    elif self._router is not None:
        adk_model = self._router.build_adk_model_for_agent(agent_name)
    else:
        adk_model = self._default_model

    return LlmAgent(
        name=agent_name.replace("-", "_"),
        model=adk_model,
        instruction=instruction,
        description=description or f"GClaw agent: {agent_name}",
        tools=tools or [],
        sub_agents=sub_agents or [],
        output_key=output_key,
    )
```

### Morning brief workflow

```python
# src/gclaw/agents/workflows/morning_brief.py
from google.adk.agents import LlmAgent, ParallelAgent, SequentialAgent
from gclaw.agents.factory import AgentFactory


def build_morning_brief(
    factory: AgentFactory,
    *,
    workspace_tools: list,
    dev_tools: list,
    research_tools: list,
) -> SequentialAgent:
    """Parallel fan-out across three briefing specialists, then a summary fold.

    Specialists are purpose-built workflow agents — they are NOT the managers.
    Each is bound directly to the domain tools it needs.
    """

    workspace_brief = LlmAgent(
        name="workspace_brief_specialist",
        model="gemini-2.5-flash",
        description="Produces a workspace morning snapshot.",
        instruction=(
            "Produce a concise morning snapshot of the user's workspace:\n"
            "1. Call list_calendar_events_today to get today's meetings.\n"
            "2. Call list_unread_email to get unread important email (max 10).\n"
            "3. Summarize in 3-5 bullets: meetings first, then top email senders/subjects.\n"
            "Keep it scannable. No greetings, no sign-offs."
        ),
        tools=workspace_tools,
        output_key="workspace_summary",
    )

    dev_brief = LlmAgent(
        name="dev_brief_specialist",
        model="gemini-2.5-flash",
        description="Produces a dev morning snapshot.",
        instruction=(
            "Produce a concise dev morning snapshot:\n"
            "1. Call list_open_prs to get open PRs awaiting the user's review or author action.\n"
            "2. Call list_failing_workflows to get any failing CI runs on active branches.\n"
            "3. Summarize in 3-5 bullets: blocking items first, then informational.\n"
            "Keep it scannable. No greetings."
        ),
        tools=dev_tools,
        output_key="dev_summary",
    )

    research_brief = LlmAgent(
        name="research_brief_specialist",
        model="gemini-2.5-flash",
        description="Produces a research morning snapshot.",
        instruction=(
            "Produce a concise research morning snapshot:\n"
            "1. Call web_search with the user's current tracked topics (from memory if available).\n"
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
        model="gemini-2.5-flash",
        description="Folds three domain snapshots into a single prioritized rundown.",
        instruction=(
            "You have three inputs in session state:\n"
            "- {workspace_summary}: calendar and email\n"
            "- {dev_summary}: PRs and CI\n"
            "- {research_summary}: articles and topics\n\n"
            "Fold into one morning brief. Lead with anything time-sensitive or blocking. "
            "Format: H2 per area (## Workspace / ## Dev / ## Research), 3 bullets max per area. "
            "End with a one-line 'Today's focus:' recommendation."
        ),
        output_key="morning_brief",
    )

    return SequentialAgent(
        name="MorningBriefWorkflow",
        sub_agents=[fan_out, summary],
    )
```

### Commit message workflow

```python
# src/gclaw/agents/workflows/commit_message.py
from google.adk.agents import LlmAgent, SequentialAgent
from gclaw.models.model_config import TaskProfile
from gclaw.routing.router import ModelRouter
from gclaw.agents.workflows.validators import ValidateCommitMsg


def build_commit_message_workflow(
    *,
    dev_tools: list,
    router: ModelRouter | None,
    default_model: str,
) -> SequentialAgent:
    """Draft → Review → Validate sequence for generating commit messages.

    The draft specialist uses the CODE_GENERATION task profile (Nemotron via
    LiteLlm when the router is wired). The reviewer uses Gemini Flash for speed.
    Validate is a custom BaseAgent that interprets the reviewer's pass/fail
    and yields either the approved draft or an actionable failure.
    """

    draft_model = (
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
            "2. Analyze the change — is it a feat, fix, docs, refactor, test, or chore?\n"
            "3. Write a commit message:\n"
            "   - Subject: imperative mood, <=72 chars, prefix with the type, no trailing period.\n"
            "   - Body (optional, blank line separator): explain *why*, not *what*.\n"
            "4. Output only the commit message. No preamble, no code fences, no explanation."
        ),
        tools=dev_tools,
        output_key="commit_draft",
    )

    reviewer = LlmAgent(
        name="style_reviewer_specialist",
        model="gemini-2.5-flash",
        description="Scores a commit message draft against GClaw's commit conventions.",
        instruction=(
            "You review commit message drafts. The draft is in session state as {commit_draft}.\n\n"
            "Check these rules:\n"
            "1. Subject line uses Conventional Commits prefix (feat/fix/docs/refactor/test/chore).\n"
            "2. Subject is <= 72 chars.\n"
            "3. Subject uses imperative mood ('add X' not 'adds X' or 'added X').\n"
            "4. If a body exists, it's separated from the subject by a blank line and explains *why*, not *what*.\n"
            "5. No trailing period on the subject line.\n\n"
            "Output exactly one of:\n"
            "- 'pass' — if all rules are satisfied\n"
            "- 'fail: <brief explanation of which rules failed and how to fix>' — otherwise"
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

### `ValidateCommitMsg`

```python
# src/gclaw/agents/workflows/validators.py
from __future__ import annotations

from typing import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.genai.types import Content, Part


class ValidateCommitMsg(BaseAgent):
    """Final gate in CommitMessageWorkflow.

    Reads session state:
      - review_status: either "pass" or "fail: <reason>"
      - commit_draft:  the drafted commit message

    Yields a single Event with the validated draft on pass, or an
    actionable failure message on fail.
    """

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        status = (state.get("review_status") or "").strip()
        draft = (state.get("commit_draft") or "").strip()

        if status.lower().startswith("pass"):
            text = f"Commit message approved:\n\n{draft}"
        else:
            reason = status[len("fail:"):].strip() if status.lower().startswith("fail:") else status
            text = (
                f"Commit message rejected.\n\n"
                f"Draft:\n{draft}\n\n"
                f"Reason: {reason or 'No reason provided by reviewer.'}\n\n"
                f"Fix the issues and re-run the workflow."
            )

        yield Event(
            author=self.name,
            content=Content(role="model", parts=[Part(text=text)]),
        )
```

### Orchestrator rewrite

```python
# src/gclaw/agents/orchestrator.py (new shape)
from google.adk.agents import LlmAgent
from google.adk.tools import agent_tool

from gclaw.agents.factory import AgentFactory
from gclaw.agents.workflows.morning_brief import build_morning_brief
from gclaw.agents.workflows.commit_message import build_commit_message_workflow
from gclaw.board.service import BoardService
from gclaw.tools import workspace_tools, dev_tools, comms_tools, research_tools, home_tools
# board tool helpers stay — create_board_task_tool, list_board_tasks_tool, etc.


def build_managers(factory: AgentFactory, board_tools: list) -> dict[str, LlmAgent]:
    """Build the five manager agents as thin routers.

    Each manager has its domain tools + the board tools (so it can
    create follow-up async tasks for work it can't finish synchronously).
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
    hm_tools = [home_tools.list_devices, home_tools.set_device_state] + board_tools
    cm_tools = [comms_tools.list_chat_spaces, comms_tools.post_chat_message] + board_tools
    rs_tools = [research_tools.web_search, research_tools.fetch_url] + board_tools

    return {
        "workspace_mgr": factory.build(
            agent_name="workspace-mgr", soul_overlay="workspace", tools=ws_tools,
            description="Routes workspace requests (Gmail/Calendar/Drive/Docs) to the single best tool.",
        ),
        "dev_mgr": factory.build(
            agent_name="dev-mgr", soul_overlay="dev", tools=dv_tools,
            description="Routes dev requests (GitHub/code/local) to the single best tool.",
        ),
        "home_mgr": factory.build(
            agent_name="home-mgr", soul_overlay="home", tools=hm_tools,
            description="Routes smart-home requests to the single best tool.",
        ),
        "comms_mgr": factory.build(
            agent_name="comms-mgr", soul_overlay="comms", tools=cm_tools,
            description="Routes inter-platform comms (chat/messaging) to the single best tool.",
        ),
        "research_mgr": factory.build(
            agent_name="research-mgr", soul_overlay="research", tools=rs_tools,
            description="Routes research requests (web search, URL fetch) to the single best tool.",
        ),
    }


def build_orchestrator(
    factory: AgentFactory,
    board_service: BoardService,
    router: ModelRouter | None = None,
    default_model: str = "gemini-2.5-flash",
    memories: list[str] | None = None,
) -> LlmAgent:
    """Build the root orchestrator with AgentTool-wrapped managers + workflows."""

    board_tools = [
        create_board_task_tool(board_service),
        list_board_tasks_tool(board_service),
        get_board_task_tool(board_service),
        complete_board_task_tool(board_service),
    ]

    managers = build_managers(factory, board_tools)

    # Build composed workflows. Each uses the same underlying tool functions
    # as the managers (shared Python callables, not duplicated instances).
    morning_brief = build_morning_brief(
        factory,
        workspace_tools=[workspace_tools.list_unread_email, workspace_tools.list_calendar_events_today],
        dev_tools=[dev_tools.list_open_prs, dev_tools.list_failing_workflows],
        research_tools=[research_tools.web_search],
    )
    commit_msg = build_commit_message_workflow(
        dev_tools=[dev_tools.get_current_diff, dev_tools.read_local_file],
        router=router,
        default_model=default_model,
    )

    orchestrator_tools = [
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

### Tool helpers

```python
# src/gclaw/tools/gws.py
import asyncio
import json
import logging

logger = logging.getLogger(__name__)


class GwsError(RuntimeError):
    pass


async def run_gws(*args: str, timeout: float = 30.0) -> dict:
    """Run the gws CLI and return parsed JSON stdout.

    Args are passed as-is to the gws binary. Raises GwsError on non-zero
    exit or invalid JSON output.
    """
    proc = await asyncio.create_subprocess_exec(
        "gws", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise GwsError(f"gws {args} timed out after {timeout}s")

    if proc.returncode != 0:
        raise GwsError(
            f"gws {args} exited {proc.returncode}: {stderr.decode(errors='replace')}"
        )

    if not stdout:
        return {}
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as e:
        raise GwsError(f"gws {args} returned non-JSON output: {e}") from e
```

```python
# src/gclaw/tools/workspace_tools.py (illustrative — full file has all 6)
import json
from gclaw.tools.gws import run_gws


async def list_unread_email(max_results: int = 10) -> str:
    """List unread email in the user's inbox.

    Args:
        max_results: maximum number of emails to return (default 10).

    Returns:
        A formatted summary of unread emails with sender, subject, and snippet.
    """
    result = await run_gws(
        "gmail", "users.messages.list",
        "--params", json.dumps({
            "userId": "me",
            "q": "is:unread in:inbox",
            "maxResults": max_results,
        }),
    )
    messages = result.get("messages", [])
    if not messages:
        return "No unread email."

    # Fetch each message header for a human-readable summary.
    lines = []
    for m in messages:
        detail = await run_gws(
            "gmail", "users.messages.get",
            "--params", json.dumps({
                "userId": "me",
                "id": m["id"],
                "format": "metadata",
                "metadataHeaders": ["From", "Subject"],
            }),
        )
        headers = {h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])}
        lines.append(f"- {headers.get('From', '?')}: {headers.get('Subject', '(no subject)')}")
    return "\n".join(lines)
```

Analogous shapes for `dev_tools.py` (using `run_gh`), `comms_tools.py`, `research_tools.py`, `home_tools.py`.

### Dockerfile change

```dockerfile
FROM python:3.12-slim

# gws binary — Google Workspace CLI
ARG GWS_VERSION=latest
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL https://github.com/googleworkspace/cli/releases/${GWS_VERSION}/download/gws-linux-x86_64.tar.gz \
       | tar -xz -C /usr/local/bin gws \
    && chmod +x /usr/local/bin/gws \
    && apt-get purge -y curl \
    && rm -rf /var/lib/apt/lists/*

# gh CLI — GitHub
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
       | gpg --dearmor -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
       > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

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

**Note**: the `GWS_VERSION=latest` arg and release URL pattern need verification against the actual `googleworkspace/cli` releases page at implementation time — if the path is wrong, the build fails loudly and we fix it. The spec doesn't assume a specific version.

## Testing strategy

**Unit tests** — every new/changed file gets one. TDD where practical (write the failing test first, implement, watch it pass).

- `test_tools_gws.py` / `test_tools_gh.py`: subprocess invocation, JSON parsing, error propagation. Mock `asyncio.create_subprocess_exec`.
- `test_workspace_tools.py` / `test_dev_tools.py`: each tool function — mock `run_gws`/`run_gh`, assert call shape and return format.
- `test_workflows_morning_brief.py`: verify `ParallelAgent` wiring, `output_key` propagation through a fake runner that records session state writes, final `SequentialAgent` shape.
- `test_workflows_commit_message.py`: `ValidateCommitMsg` pass path (status=`pass` → draft in output), fail path (status=`fail: xyz` → feedback in output).
- `test_factory_output_key.py`: factory passes `output_key` through to `LlmAgent`.
- `test_router_build_adk_model.py`: router returns strings for Gemini, `LiteLlm` instances for OpenRouter, handles `openrouter/...` prefix correctly.

**Integration tests** — end-to-end, one per major flow.

- `test_orchestrator_agenttool.py`: constructs the full orchestrator with AgentTool-wrapped managers, feeds it a multi-step prompt via a mock `Runner` or recorded LLM responses, asserts that the root stays in control between sub-agent calls (i.e., the "receptionist" bug does not recur).
- `test_integration_litellm_providers.py`: replaces the deleted `test_integration_providers.py`. Asserts that dev-mgr (routed to Nemotron via CODE_GENERATION profile) is built with a `LiteLlm` model instance, and that the orchestrator can successfully AgentTool-call it without hitting the RemoteRunner path (which no longer exists).

**Regression tests** — ensure existing behavior preserved.

- Existing `test_dispatcher.py` tests for memory auto-recall/auto-capture still pass (minus the two deleted `remote_runner` tests).
- Existing `test_board_*` tests unchanged.

**Manual smoke tests** (not in the automated suite, but documented in the plan):

- Run the server locally with `MODEL_ROUTING_ENABLED=true`, real `OPENROUTER_API_KEY`, and a local `gws` install. Hit `/chat` with "what's my morning look like" and verify the workflow fires. Hit `/chat` with "draft a commit for my current diff" and verify the commit workflow fires.

## Migration order (implementation sequencing)

This order minimizes broken intermediate states.

1. **Router + factory foundation.** Add `build_adk_model_for_profile` and `build_adk_model_for_agent` to router, `output_key` to factory, factory switches from `resolve_for_agent` to `build_adk_model_for_agent`. No behavioral change for Gemini agents; Nemotron agents now construct via LiteLlm. Tests for both. ← *fully green after this task*
2. **Tool helpers.** `gws.py`, `gh.py`, plus all five `*_tools.py` files. Unit tests with mocked subprocess. No wiring yet. ← *still green*
3. **Workflow specialists.** `workflows/morning_brief.py`, `workflows/commit_message.py`, `workflows/validators.py`. Unit tests. ← *still green*
4. **Scaffold missing agent configs.** `agents/home-mgr.md`, `agents/comms-mgr.md`, `agents/research-mgr.md`, `soul/home.md`, `soul/comms.md`, `soul/research.md`. Just file creation. ← *still green*
5. **Orchestrator rewrite.** Replace `orchestrator.py`. Wire all AgentTools. ← *integration test starts passing*
6. **Delete RemoteRunner + simplify AgentRunner.** Remove the file, the runner branch, the ctor param, the tests. Simplify `ModelEndpoint` to drop `api_base`/`api_key_env`/`is_remote`. Update `main._build_model_router`. ← *dispatch path simplifies, tests stay green*
7. **Dockerfile.** Add `gws` and `gh` install steps. Verify the image builds cleanly (manual or CI).
8. **Final verification.** Full test suite, then the manual smoke test against a live OpenRouter + a dev `gws` install.

Each task is one TDD cycle (write failing test → implement → pass → commit). Tasks 1–4 are independent and could run in parallel if using subagent-driven-development.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| `gws` release URL path differs from the Dockerfile assumption. | Build fails loudly. Fix URL in a follow-up commit. Not a spec blocker. |
| LiteLlm doesn't support the exact Nemotron model ID on OpenRouter. | `litellm.model_list` and the `openrouter/` prefix are documented. If the exact ID fails, fall back to `openrouter/<same-id>` without prefix stripping. A unit test covers both shapes. |
| Session-state sharing between `ParallelAgent` sub-agents is not automatic in older ADK versions. | The ADK blog post (cited in references) explicitly demonstrates this works via `output_key`. If a test surfaces a problem, pin to the ADK version the blog post uses. |
| `workflow_brief_specialist` instances may get served by a rate-limited Nemotron tier (CODE_GENERATION profile). | Workflow specialists are explicitly routed to `gemini-2.5-flash` by hardcoded `model=` in this spec — they don't use the factory's profile-based routing. Only `commit_draft_specialist` uses Nemotron. |
| Dockerfile install of `gh` via apt requires newer Ubuntu/Debian repos than `python:3.12-slim` ships. | Fall back to downloading the `gh` binary directly from GitHub releases, same pattern as `gws`. |
| Breaking change to existing Cloud Run deployment if Workspace credentials aren't provisioned. | Spec treats Workspace auth wiring as a **deployment-time** concern. The code falls back gracefully: workspace tool functions wrapped in try/except that returns "Workspace access not configured." Deployment engineers set `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` when ready. |

## Out of scope (follow-up specs)

- **Memory layer upgrade** (always-on agent with ingest/consolidate/query) — next spec.
- **Skill design patterns** (Tool Wrapper / Generator / Reviewer / Inversion / Pipeline) formalization — third spec.
- **Research on `GoogleCloudPlatform/generative-ai` repo** for additional use-case discovery — fourth spec.
- **Real Home API integration, real web search API, real comms integrations beyond `gws chat`** — each its own small spec/plan.
- **Three-tier specialist hierarchy** (dynamic specialist spawning under managers) — deferred.
- **Cron system wiring for the morning brief trigger** — cron infrastructure exists; wiring a specific cron is a user-action task, not a code change.

## Acceptance criteria

The refactor is complete when:

1. `orchestrator.py` has zero `sub_agents=[...]` uses and all delegation happens through `agent_tool.AgentTool`.
2. `RemoteRunner` and its tests are deleted. `grep -r RemoteRunner` returns no hits.
3. All five manager config files exist: `workspace-mgr`, `dev-mgr`, `home-mgr`, `comms-mgr`, `research-mgr` in `agents/`, with matching soul overlays in `soul/`.
4. `test_orchestrator_agenttool.py` passes — demonstrating the root orchestrator completes a multi-step composed request without losing control (no "receptionist" regression).
5. `test_integration_litellm_providers.py` passes — demonstrating dev-mgr (Nemotron via OpenRouter) executes through ADK's native Runner via LiteLlm, not through a side channel.
6. `test_workflows_morning_brief.py` and `test_workflows_commit_message.py` both pass — demonstrating both composition patterns (ParallelAgent+SequentialAgent and SequentialAgent+Reviewer+Validate) work.
7. Full test suite green: `python3 -m pytest tests/ -q` exits 0.
8. Docker image builds successfully with `gws` and `gh` binaries on `$PATH`.

## References

- `docs/superpowers/plans/2026-04-04-multi-provider-routing.md` — the prior plan this partially supersedes (the `RemoteRunner` path it introduced is being retired).
- Google Cloud blog: "Build multi-agentic systems using Google ADK" (Ashwini Kumar, Neeraj Agrawal, July 2025) — the source of the AgentTool / ParallelAgent / SequentialAgent / Reviewer patterns used throughout this spec.
- `github.com/googleworkspace/cli` — the `gws` CLI used for Google Workspace tool wrappers.
- `github.com/GoogleCloudPlatform/generative-ai/tree/main/gemini/agents/always-on-memory-agent` — reference for the next spec (memory layer upgrade).
- Google Cloud Tech on X: "5 Agent Skill design patterns every ADK developer should know" (Mar 2026) — reference for the third spec (skill patterns).
