# Cloud Run + Memory Bank — reference validation

**Date:** 2026-04-11
**Reference:** [`agents/cloud_run/agents_with_memory/get_started_with_memory_for_adk_in_cloud_run.ipynb`](https://github.com/GoogleCloudPlatform/generative-ai/blob/main/agents/cloud_run/agents_with_memory/get_started_with_memory_for_adk_in_cloud_run.ipynb) (shallow clone at `/tmp/genai-samples/`)
**GClaw files reviewed:** `src/gclaw/memory/client.py`, `src/gclaw/memory/service.py`, `src/gclaw/main.py::_build_memory_service`, `src/gclaw/main.py::_build_heartbeat_service`, `src/gclaw/dispatch/runner.py`, `src/gclaw/agents/orchestrator.py`.
**Purpose:** The generative-ai samples survey (`2026-04-11-generative-ai-samples-survey.md`) flagged this notebook as the highest-ROI validation step for GClaw's memory wire-up. This doc diffs the reference pattern against GClaw line-by-line and classifies each divergence.

## TL;DR

**No blocking bugs.** GClaw's memory architecture is functionally equivalent to the reference — same Vertex AI Memory Bank surface, same scope semantics, same auto-recall + auto-capture loop.

**One significant tech-debt item**: we built `MemoryBankClient` as a parallel implementation of ADK's native `VertexAiMemoryBankService`. A full migration to the native service is a separate plan and is already listed under "Out of scope" in the loose-ends plan this commit closes out.

**Two smaller divergences worth noting** but not fixing now: no `PreloadMemoryTool` usage, and our Cloud Run deployment path is custom rather than `adk deploy cloud_run`. Both are intentional.

## The reference recipe (10-line version)

1. Enable Cloud Run + Vertex AI APIs on a GCP project.
2. `client = vertexai.Client(project=..., location=...)`.
3. `agent_engine = client.agent_engines.create(config={"display_name": ..., "context_spec": {"memory_bank_config": {"generation_config": {"model": "gemini-2.5-flash"}}}})` — this returns an Agent Engine resource whose `api_resource.name` ends with `reasoningEngines/{id}`. **No agent is actually deployed** to Agent Engine — the resource just hosts the Sessions and Memory Bank for the given id.
4. `session_service = VertexAiSessionService(project=..., location=..., agent_engine_id=...)` — ADK-native, persists sessions inside the Agent Engine.
5. `memory_service = VertexAiMemoryBankService(project=..., location=..., agent_engine_id=...)` — ADK-native, persists memories inside the Agent Engine.
6. Agent is constructed with `tools=[..., PreloadMemoryTool()]` — ADK builtin that auto-injects memories into the prompt from the current memory service.
7. `runner = Runner(app_name=..., agent=..., session_service=..., memory_service=...)` — ADK Runner takes both services at construction time.
8. Call `runner.run(user_id=..., session_id=..., new_message=...)` — the Runner coordinates session persistence, memory lookup, and auto-capture.
9. Deploy: `adk deploy cloud_run --session_service_uri=agentengine://{id} --memory_service_uri=agentengine://{id} --app_name {name} .` — the `agentengine://` URI scheme tells the deployed ADK app to wire the two services at startup automatically.
10. Clean up: `client.agent_engines.delete(name=...)` + `gcloud run services delete`.

## Diff table: reference vs GClaw

| # | Dimension | Reference | GClaw | Status |
|---|---|---|---|---|
| 1 | GCP API enablement | `run.googleapis.com`, `aiplatform.googleapis.com`, `artifactregistry.googleapis.com`, `cloudbuild.googleapis.com` | Same set — `cloudbuild.yaml` targets these services. | **ALIGNED** |
| 2 | Agent Engine resource | Created via `client.agent_engines.create(...)` inside the notebook. Returns `api_resource.name` → extracted numeric id. | Pre-provisioned out-of-band. `MEMORY_BANK_REASONING_ENGINE_ID=1568060811371347968` in `.env`. `_build_memory_service` extracts the numeric id from a full path if given. | **ALIGNED** — GClaw's approach is correct for a long-lived app; the notebook creates-then-deletes because it's a tutorial. |
| 3 | Memory Bank URL surface | `VertexAiMemoryBankService` hits `reasoningEngines/{id}/memories:*` internally. | `MemoryBankClient._base_url` = `…/reasoningEngines/{id}` — fixed in commit `0d4caa3`. | **ALIGNED** |
| 4 | Memory service implementation | ADK-native `VertexAiMemoryBankService` (subclass of `BaseMemoryService`). | Custom `MemoryBankClient` (HTTP client) + `MemoryService` wrapper. | **DIVERGENT (tech debt)** — functionally equivalent but we carry ~200 LoC of code that ADK ships for free. **Follow-up: separate migration plan.** |
| 5 | Session service — live state | `InMemorySessionService` (notebook dev mode) OR `VertexAiSessionService` (Cloud Run). | `InMemorySessionService` for the ADK Runner's live state. | **ALIGNED** for dev mode. |
| 6 | Session service — persistence | `VertexAiSessionService` stores sessions inside the Agent Engine resource. | Custom `SessionService` backed by `SessionRepo` in Firestore (`users/{uid}/sessions/{id}`). Wired into `AgentRunner` as `session_store` — per-turn mirroring + end-of-session extraction. | **DIVERGENT (intentional)** — Firestore lets us own data locality, query sessions with other board/cron state in a single backend, and side-step the Agent Engine tenancy semantics. Cost: ~350 LoC of custom session code. Trade-off is worth it while Agent Engine Sessions is still stabilising. |
| 7 | Memory injection into prompt | `PreloadMemoryTool` ADK builtin — fetches memories at tool-call time and adds them to the model's context. | `AgentRunner.run` wraps the user message with `[Recalled memories]\n...\n[User message]\n...`, and each manager has a `before_agent_callback` that pulls agent-scoped memories and returns a `types.Content` block. | **DIVERGENT (intentional)** — our approach is more invasive but gives us control over formatting (`format_for_prompt` groups by topic + sorts by importance) and over scoping (per-manager recall). `PreloadMemoryTool` would be easier but less flexible. |
| 8 | Auto-capture after turn | `add_session_to_memory` callback — reads session events and calls `memory_service.add_session_to_memory(session)`. | `AgentRunner.run` fires `memory_service.capture(...)` as a fire-and-forget background task (via `asyncio.create_task` + `_pending_captures` set). | **ALIGNED** in intent. GClaw does this per-turn, the reference does it on session end. |
| 9 | End-of-session extraction | Reference assumes session end is explicit via `VertexAiSessionService.delete_session` or similar. | `POST /chat/end` route → `AgentRunner.end_session` → delegates to `SessionService.end_session` (Firestore mark-ended + `memory_service.generate_memories`) when `session_store` is set. Heartbeat loop auto-ends stale sessions past `STALE_SESSION_THRESHOLD_SECONDS`. | **ALIGNED** — richer in GClaw (auto-end sweep), same spirit. |
| 10 | Agent tools | Regular Python functions (`get_weather`) wrapped by ADK. | Full tool stack: `tools/{gws,gh,workspace_tools,dev_tools,comms_tools,research_tools,home_tools,governance}.py` plus board function tools. | **ALIGNED** — more tools, same pattern. |
| 11 | Model routing | Single Gemini 2.5 Flash model. | `ModelRouter` + `LiteLlm` for multi-provider (Gemini/Gemma/Nemotron via OpenRouter or NIM). | **DIVERGENT (intentional)** — GClaw's routing layer is additive; the reference doesn't need it. |
| 12 | Cloud Run deployment | `adk deploy cloud_run --session_service_uri=agentengine://... --memory_service_uri=agentengine://... .` — one command, ADK generates the Dockerfile and service wiring. | Custom `Dockerfile` + `cloudbuild.yaml` targeting the user's GCP project. FastAPI app, not the ADK-generated web UI. | **DIVERGENT (intentional)** — GClaw has FastAPI routes beyond what ADK's auto-generated app provides (board CRUD, cron routes, heartbeat, auth middleware, routing admin). `adk deploy cloud_run` wouldn't know about any of these. |
| 13 | Auth | `--allow-unauthenticated` in the tutorial. | Firebase Auth middleware (`firebase_auth_enabled=true` in prod), DevUserMiddleware in dev mode. | **ALIGNED** — GClaw is production-grade, reference is demo-grade. |
| 14 | Memory shape | Whatever `VertexAiMemoryBankService` surfaces; the notebook doesn't inspect shape. | `Memory` model carries `fact/summary/entities/topics/importance` (Item D this session). | **ALIGNED** — GClaw is richer, reference is opaque. |
| 15 | Env vars | `GOOGLE_GENAI_USE_VERTEXAI=TRUE`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`. | `GCP_PROJECT_ID`, `GCP_LOCATION`, `MEMORY_BANK_REASONING_ENGINE_ID`, `MEMORY_ENABLED`, plus application-specific vars. | **DIVERGENT (not a bug)** — naming differs but the GClaw settings at `src/gclaw/settings.py` resolve the same values. Worth documenting in `.env.example` that `GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION` are also expected by `google.auth` at the process level, but that's already the case because we use `google.auth.default()` in `_build_memory_service`. |

## Fix-now list

**Empty.** Nothing in the diff is a bug. No environment variable is misnamed, no auth scope is missing, no URL is wrong, no data is being lost.

## Follow-up plans (in priority order)

### 1. `VertexAiMemoryBankService` migration (biggest payoff)

**Scope:** Delete `src/gclaw/memory/client.py` (200+ LoC) and replace `MemoryService` with a thin wrapper over ADK's `VertexAiMemoryBankService`. `AgentRunner` currently calls `memory_service.recall(...)` / `memory_service.capture(...)` directly — neither method exists on `BaseMemoryService`. The migration therefore requires either:

- **Option A** (lean): keep our `MemoryService` interface, have it delegate to `VertexAiMemoryBankService.search_memory(...)` and `add_session_to_memory(...)` under the hood. Smallest surface change. Our `format_for_prompt`, importance-ranked sort, agent-scoped recall callbacks all keep working as-is.
- **Option B** (full): adopt `PreloadMemoryTool` + remove `AgentRunner`'s custom recall/capture hooks entirely. Bigger blast radius: delete ~100 LoC in `dispatch/runner.py`, delete `before_agent_callback` plumbing in `orchestrator.py`, re-architect the custom-formatting path.

**Recommendation: Option A.** It closes the tech-debt gap without regressing GClaw's control over memory shape. Estimated effort: 4-6 hours. Blockers: need to confirm that `VertexAiMemoryBankService.search_memory` supports scope filtering the way our `MemoryScope` does.

### 2. `PreloadMemoryTool` as an optional alternative injection path

**Scope:** Add `PreloadMemoryTool` to the orchestrator tool list behind a settings flag (`GCLAW_USE_PRELOAD_MEMORY_TOOL=false` default). When enabled, the per-manager `before_agent_callback` pathway becomes redundant and can be removed. This lets us A/B-test the reference's auto-injection approach against our custom approach. Only worth pursuing after the migration in #1.

### 3. Programmatic Agent Engine creation

**Scope:** Add a one-shot script at `scripts/create_agent_engine.py` that runs `client.agent_engines.create(...)` and prints the resulting numeric id. Today we assume the engine is provisioned out-of-band and the id is copied into `.env` by hand. Not a bug but it's the one setup step that isn't idempotent via `cloudbuild.yaml`.

## Methodology

1. `git clone --depth 1 https://github.com/GoogleCloudPlatform/generative-ai.git /tmp/genai-samples` (done in the survey pass; still present).
2. Extracted all markdown + code cells from `get_started_with_memory_for_adk_in_cloud_run.ipynb` via Python `json.load`.
3. For each step in the reference recipe, grepped the GClaw source tree for the corresponding symbol or config key (`VertexAiMemoryBankService`, `PreloadMemoryTool`, `agent_engines.create`, `MEMORY_BANK_REASONING_ENGINE_ID`, etc.).
4. Classified each divergence as `ALIGNED`, `DIVERGENT (intentional)`, `DIVERGENT (bug)`, or `DIVERGENT (tech debt)`.
5. Produced the fix-now list (empty) and the follow-up plan list (three items).

No code changes in this item. Validation was the entire output.
