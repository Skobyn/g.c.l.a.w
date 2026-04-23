---
name: gclaw-conventions
description: >
  gclaw-specific patterns layered on top of ADK — the manager /
  specialist tier model, the AgentTool wrapping convention, the
  board-mediated communication rule, the soul overlay system, the
  factory + agent_config_service registration path. Use when adding
  or modifying any agent inside gclaw. Pair with `adk-patterns` for
  the underlying ADK API reference.
metadata:
  author: gclaw
  version: 1.0.0
---

# gclaw Conventions

This skill captures the patterns that gclaw layers on top of vanilla
ADK. The `adk-patterns` skill covers the ADK Python API; this one
covers gclaw's wrapping of it.

## Three-tier agent hierarchy

```
Root Orchestrator (single entry point — Gemini, conversational)
  ├── Workspace Manager (Gmail / Calendar / Drive — router only)
  ├── Dev Manager (GitHub / local repo — router only)
  ├── Home Manager (smart home — router only)
  ├── Comms Manager (Google Chat — router only)
  ├── Research Manager (web search / fetch — router only)
  ├── Profile Manager (user.md owner)
  ├── Content-Scott / Content-Apex (brand-pinned content pipelines)
  └── Specialists (dynamic, spawned per task by managers)
```

Three rules that don't bend:

1. **AgentTool, never sub_agents=**. Managers attach to the orchestrator
   as `agent_tool.AgentTool(agent=manager)` instances on the
   orchestrator's `tools=` list — NOT via ADK's `sub_agents=` parameter.
   See `src/gclaw/agents/orchestrator.py::build_orchestrator` and the
   docstring there enforces this.
2. **Async hand-offs go through the board, not direct messaging.**
   When manager A needs manager B to do something later, A creates a
   board task assigned to B. A heartbeat picks it up. Anything that
   looks like A directly invoking B's AgentTool synchronously for
   non-blocking work is a bug — that pattern is reserved for HIGH
   priority inline dispatch only (see priority gating below).
3. **Managers are routers, specialists do work.** Manager bodies
   should be one paragraph: "you route to the single best tool, you
   do not synthesize." Don't put long instructions on managers — put
   them on specialists.

## Agent file structure

Every agent has TWO halves:

- **`agents/<name>.md`** — role, capabilities, tool grants, escalation
  rules. Public to the agent's instruction prompt. May start with a
  YAML frontmatter block for `heartbeat:` config.
- **`soul/<name>.md`** — personality, voice, preferences. Layered onto
  `soul/base.md` for the agent. Stays generic in the public repo;
  brand-specific personalities live in the maintainer's overlay
  (`GCLAW_CONFIG_DIR` rsync).

The system prompt for agent X is assembled by `ConfigLoader.build_system_prompt`:

```
soul/base.md
  + soul/<X>.md (overlay)
  + agents/<X>.md (body)
  + injected memories (when memory_service is wired)
  + skill stubs (when skill_registry is wired)
```

If `agent_config_service.get_override(X)` returns an override with
`body_override`, that REPLACES the baseline `agents/<X>.md` body —
it does not merge. Same for `soul_overlay`. Edit overrides
through `/admin/agents/<name>` (PATCH), never edit the .md files
on disk for runtime-only changes.

## Priority-gated dispatch (orchestrator → manager)

Every `create_board_task` MUST set a `priority`, and the priority
determines whether the orchestrator ALSO invokes the manager in the
same turn:

- **HIGH** — user is waiting. Set `priority="high"`, then call the
  manager's AgentTool in the SAME turn. Synchronous, streams events
  back into the chat.
- **MEDIUM** — useful background work in ~15min. Queue only. The
  manager's heartbeat picks it up.
- **LOW** — hygiene / nice-to-have. Queue only.

Never set HIGH and then forget to invoke — the user sees a stuck task.

## Adding a new agent

A complete new agent requires:

1. `agents/<name>.md` — body (frontmatter optional for heartbeat).
2. `soul/<name>.md` — voice (placeholder OK; overlay supplies real
   personality).
3. **Tool grants**: register the agent's tools in the factory call
   that builds it. Either:
   - **For a Manager**: add a tuple to the `specs:` list in
     `src/gclaw/agents/orchestrator.py::build_managers`, with
     `required=False` if the agent is optional. The factory will
     skip optional managers when their .md is missing.
   - **For a Standalone agent** (added at runtime, not in the source
     tree): use `agent_config_service.create_standalone(...)`. The
     architect agent uses this path.
4. **Wire into the orchestrator's tool list** if it's a manager: add
   to the `optional_key` loop or the explicit list in
   `build_orchestrator`.
5. **Update the orchestrator's `Available Managers` section** in
   `agents/orchestrator.md` (or the override's `body_override`) so the
   orchestrator's prompt actually knows the new agent exists. Without
   this, the agent loads fine but the orchestrator never delegates to
   it.
6. **Heartbeat (optional)**: add `heartbeat.enabled: true` to the
   agent's frontmatter to wake it on the schedule. Default 15m.

## Tool definitions

Tools are plain Python functions. ADK introspects the signature to
build the JSON schema; **type-annotate every parameter** or ADK rejects
the tool. Never use string forward references that depend on
TYPE_CHECKING imports — `typing.get_type_hints` will fail at runtime
(see `src/gclaw/agents/orchestrator.py::get_board_task` history; PR #32
fixed a regression here).

Pattern:

```python
def my_tool(arg1: str, arg2: int = 5, tool_context: Any = None) -> str:
    """One-line summary that the LLM reads.

    More docstring here is also passed to the LLM as the tool
    description. Be precise about what it does and the side effects.
    """
    ...
```

`tool_context` is auto-injected by ADK based on the parameter NAME
(falls back when the type annotation isn't a resolvable `ToolContext`).
Use it to read `tool_context.agent_name` for the calling agent's name.

## Model resolution

The factory resolves a model in this priority order:

1. Explicit `model=` arg to `factory.build()`
2. `agents/<name>.md` frontmatter `model:` field
3. Override-stored `model.primary` (Firestore via agent_config_service)
4. Router default (catalog-resolved per task profile)
5. `_default_model` constant

Refs in override `model.primary` accept either:
- `"gemini-2.5-flash"` (bare model id, ambiguous if multiple providers
  have a model by that id — falls to first match)
- `"Anthropic/claude-haiku-4-5"` (provider-name/model-id, explicit)

For the dual-Gemini case (Vertex via System Google + public API via
Google Gemini provider with key), use the explicit form to avoid
ambiguity.

## Standalone vs file-backed agents

- **File-backed**: `agents/<name>.md` + `soul/<name>.md` checked into
  the repo. Loaded at startup by the factory.
- **Standalone (Firestore-only)**: created at runtime via
  `agent_config_service.create_standalone(agent_name, body, ...)`.
  No file; the override IS the source of truth. Persists across
  restarts. Used by the `agent-architect` to create agents on demand.

When deleting a standalone agent, pass `force=true` to
`/admin/agents/{name}` DELETE — protected agents (workspace-mgr,
dev-mgr, etc.) refuse delete without it.

## Where to read the wiring

- `src/gclaw/main.py` — composition root. ModelRouter, MemoryService,
  BoardService, AgentFactory, root orchestrator, AgentRunner all
  built here and threaded into `create_app`.
- `src/gclaw/agents/factory.py` — `AgentFactory.build()` is the only
  way to construct an LlmAgent.
- `src/gclaw/agents/orchestrator.py` — `build_managers` (the spec
  loop) and `build_orchestrator` (assembles tools).
- `src/gclaw/config/agent_config_service.py` — Firestore-backed
  override CRUD. `create_standalone`, `upsert_override`,
  `delete_override`.
- `src/gclaw/board/service.py` — board task lifecycle. Note: only the
  task assignee can `pick_up`, and `get_board_task`'s side-effect
  pickup is gated on the calling agent matching the assignee (PR #31).
- `src/gclaw/skill/registry.py` — `SkillRegistry.discover_from_dir`
  scans `skills/` for `skill.json` or `SKILL.md` and registers them.
