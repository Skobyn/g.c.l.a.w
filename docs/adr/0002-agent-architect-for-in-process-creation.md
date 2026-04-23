# ADR-0002: agent-architect for in-process agent creation

**Status:** Accepted (2026-04-22)
**Context:** gclaw can already create new agents via the admin UI's
`POST /admin/agents` (file-backed) or `agent_config_service.create_standalone`
(Firestore-only), but neither path has a *conversational* interface.
The user has to know the schema, write the body themselves, decide
manager-vs-specialist, pick a model. Most of that is judgement work
that could be delegated to an agent.

## Decision

Add an in-process `agent-architect` agent (optional manager) that:

1. Reads existing agent files via tool grants to inspect prevailing
   conventions.
2. Drafts new agent bodies + soul overlays, consulting the
   `adk-patterns` and `gclaw-conventions` skills.
3. Stages drafts via `context_write` to the shared-context blackboard.
4. Waits for explicit user approval before registering.
5. Registers via `register_standalone_agent` (recommended) or
   `write_agent_file` + `write_soul_file` (file-backed).

The architect is in-process — it joins the running gclaw graph,
shares the board / memory / soul stack, and lives in the same Cloud
Run service. It does not stand up new Cloud Run instances per agent.

## Why in-process and not "scaffold-then-deploy"

The scaffold-and-deploy pattern (`agents-cli scaffold create <name>`
+ `agents-cli deploy`) yields a new Cloud Run service per agent. That
breaks gclaw's:

- **Shared board** — the board is a Firestore collection scoped per
  user. Cross-service hand-offs would require the new service to
  speak the same Firestore schema, deploy with the same
  `GCLAW_USER_ID`, and trust the same auth — basically be gclaw.
- **Shared memory** — Vertex AI Memory Bank scoping is per agent;
  multiple services calling Memory Bank for the same user is fine,
  but adds latency and token cost vs. in-process recall.
- **Shared soul** — `soul/base.md` injection happens in the factory;
  a separate service has to re-implement it.
- **Inter-agent invocation** — orchestrator → manager today is an
  AgentTool call (in-process function call). Manager-as-service
  would need HTTP, retries, auth, timeouts, and circuit breakers.

In-process avoids all of that. The architect uses the existing factory
+ agent_config_service, which were built for exactly this.

## Tools the architect gets

Defined in `src/gclaw/tools/agent_architect_tools.py`:

| Tool | Purpose |
|---|---|
| `read_agent_file(name)` | Inspect existing baseline `.md` body |
| `read_soul_file(name)` | Inspect existing baseline soul overlay |
| `list_agent_files()` | Enumerate baseline files in `GCLAW_CONFIG_DIR/agents` |
| `list_registered_agents()` | Enumerate everything (baseline + standalone) via service |
| `write_agent_file(name, body, allow_overwrite=False)` | Write `agents/<name>.md` (file-backed creation path) |
| `write_soul_file(name, body, allow_overwrite=False)` | Write `soul/<name>.md` |
| `register_standalone_agent(name, body, ...)` | Firestore-only registration; preferred path |
| `update_agent_model(name, primary)` | Patch existing agent's model |

Plus board tools (so the architect can hand off source-tree edits to
`dev-mgr`) and context tools (for staging drafts).

All file-write tools refuse to overwrite without `allow_overwrite=True`,
and all path operations are guarded against traversal escaping
`GCLAW_CONFIG_DIR`.

## Approval gate

The architect's pipeline ends with a draft staged in
`context-queue/agent-drafts/<name>` and a one-line summary returned to
the orchestrator. **The agent does not register without explicit
human approval** ("looks good", "ship it", "register"). This is
enforced by the agent's prompt and by the `gclaw-conventions` skill
that guides its behavior.

If we want to remove human-in-the-loop later (e.g., for trusted
trajectories), the gate becomes a board task with `requires_approval=True`.

## Wiring

- `agents/agent-architect.md` — body
- `soul/agent-architect.md` — placeholder voice
- Spec entry in `build_managers` (`required=False`) so forks without
  Firestore can drop the agent without breaking the orchestrator.
- Optional-tool loop in `build_orchestrator` adds the AgentTool when
  the manager is present.
- Mention in `agents/orchestrator.md`'s **Available Managers** so the
  orchestrator's prompt knows to delegate here when the user asks
  for new agents.
- Wired into `main.py` via `set_agent_config_service(agent_config_service)`
  before the factory is built.

## What the architect does NOT do

- It does not edit `factory.py`, `orchestrator.py`, or any other
  Python file. Source-tree changes (new tools, new manager spec
  entries, new wiring) are `dev-mgr`'s job. The architect creates a
  board task with the exact diff it wants.
- It does not deploy. After registration, standalone agents work
  immediately on next `factory.build` call. File-backed agents need
  a process restart to be picked up at boot — the architect notes
  this in its completion summary so the user knows whether to bounce
  the service.
- It does not modify protected agents (orchestrator, the seven
  required managers) without explicit user permission per request.

## Open questions for follow-up

- **Tool grants for new agents**: standalone agents created via the
  service have no specific tools — they inherit nothing. We need a
  story for how the architect grants tools to a new specialist
  (currently: it asks `dev-mgr` to write a new spec entry). A
  cleaner future model: tool-binding-by-name in the override, where
  the override stores `tools: ["postiz_create_draft", "web_search"]`
  and the factory binds them by name from a tool registry. Out of
  scope for this ADR.
- **Eval gate**: ADR-0006 covers wiring evals into the architect's
  pipeline. Until then, "is the new agent any good?" is a vibes check.
