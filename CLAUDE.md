# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GClaw is a **multi-agent AI orchestration platform** built on the Google stack. It uses the Google Agent Development Kit (ADK) for agent execution and Gemini models for intelligence, with a custom orchestration layer on top (Approach B — hybrid architecture).

Two first-class surfaces:
- **Python backend** (`src/gclaw/`) — FastAPI app, ADK agents, Firestore persistence. Packaged with `hatchling`, managed with `uv`.
- **Next.js web client** (`web/`) — PWA, Firebase Auth, chat + voice UI.

## Commands

### Python (backend)

Dependencies are locked in `uv.lock`; use `uv` for all Python work.

```bash
# Install (editable + dev extras)
uv sync --extra dev

# Run the FastAPI app locally on :8080
uv run python -m gclaw.main

# Full test suite
uv run pytest

# Single file / single test
uv run pytest tests/test_model_router.py
uv run pytest tests/test_model_router.py::test_routes_code_generation_to_nemotron -xvs
```

Pytest is configured in `pyproject.toml`: `asyncio_mode = "auto"`, `pythonpath = ["src"]`. There is no separate lint step configured — match existing style.

### Web (frontend)

```bash
cd web
npm install
npm run dev     # next dev
npm run build   # next build
npm run lint    # next lint
npm test        # vitest run
npm run test:watch
```

### Container / deploy

```bash
# Build locally
docker build -t gclaw .

# Cloud Build → Artifact Registry → Cloud Run (see scripts/deploy.sh
# for the full env-var-driven wrapper; below is the bare gcloud form).
gcloud builds submit --project <your-gcp-project> --config cloudbuild.yaml
```

The Dockerfile also installs the `gh` and `gws` (Google Workspace) CLIs — the dev and workspace managers shell out to them as tools.

## Architecture (Five Layers)

1. **User Layer** — PWA web app (`web/`), Gemini Live voice (`src/gclaw/voice/`, `api/voice_ws.py`), Firebase Auth.
2. **Orchestration Layer** (custom) — Agent hierarchy, kanban project board, cron scheduler, session router. The differentiating layer.
3. **Agent Layer** (ADK) — Specialist and manager agents with Gemini, tool bindings, instructions. Managers are wrapped as ADK `AgentTool`s on the orchestrator (not `sub_agents=`); async hand-offs between agents go through the project board, not direct messaging.
4. **Memory Layer** — Firestore (sessions, board, config), Vertex AI Memory Bank (long-term recall), `soul/*.md` profiles.
5. **Integration Layer** — Extensible tool modules in `src/gclaw/tools/` (Google Workspace, GitHub, comms, home, research).

### Agent model

Every agent has two halves:
- **`agents/<role>.md`** — Role, capabilities, tool grants, authority level, escalation rules.
- **`soul/<role>.md`** — User-specific personality, preferences, communication style (evolves over time).

System prompt for an agent = its `agent.md` + matching `soul.md` + injected memories from Memory Bank. The stitching lives in `src/gclaw/config/loader.py` and `src/gclaw/agents/factory.py`.

### Hierarchy

- **Root Orchestrator (Soul)** — Single entry point. Intent classification, session continuity, personality, escalation handling. Built in `src/gclaw/agents/orchestrator.py`. Managers are attached as `AgentTool`s, not `sub_agents=` — the orchestrator's docstring enforces this.
- **Managers** (fixed tier) — Seven domain owners: **Workspace, Dev, Home, Comms, Research, Profile, Content**. Read/write the project board, can spawn specialists. Definitions in `agents/*-mgr.md`. `profile-mgr` owns `user.md`; `content-mgr` runs the social-content pipeline.
- **Specialists** (dynamic tier) — Short-lived ADK agents spawned by managers for single tasks. Bound to specific tools.

### Wiring (where to start reading)

`src/gclaw/main.py` is the composition root — it builds the `ModelRouter`, `MemoryService`, `BoardService`, `AgentFactory`, root orchestrator, `AgentRunner`, and hands them to `create_app` in `src/gclaw/api/app.py`. When adding a new subsystem, thread it through both files.

Key packages under `src/gclaw/`:
- `api/` — FastAPI routers (`chat`, `board`, `cron`, `heartbeat`, `onboarding`, `connection`, `routing`, `voice_ws`, `admin`) and `app.py` factory.
- `agents/` — `factory.py` (builds ADK agents from config), `orchestrator.py` (root), `workflows/` (deterministic multi-step flows like `morning_brief`, `commit_message`).
- `board/` — Kanban service on top of Firestore (`firestore/board_repo.py`).
- `routing/router.py` + `models/model_config.py` — ModelRouter that maps `TaskProfile` → `ModelEndpoint`. Non-Gemini providers (e.g. OpenRouter/Nemotron) are wrapped with ADK's `LiteLlm` adapter inside the router, not at call sites.
- `memory/` — Vertex AI Memory Bank client + consolidation service.
- `heartbeat/` — Periodic context/consolidation service.
- `cron/` — Scheduled job service (pairs with `crons/` at repo root).
- `skill/` — Skill discovery/loader/registry for the `skills/` directory.
- `tools/` — Tool implementations bound to managers: `gws.py`, `gh.py`, `comms_tools.py`, `dev_tools.py`, `home_tools.py`, `research_tools.py`, `workspace_tools.py`, `postiz_tools.py`, `image_gen_tools.py`, `user_profile_tools.py`, `context_tools.py`, plus `governance.py`. `tools/catalog/` reflects `@tool_export`-decorated callables into Firestore; `tools/mcp/` hosts MCP client integration; `tools/code_exec/` holds the local + remote sandbox runners.
- `auth/middleware.py` — `FirebaseAuthMiddleware`. When auth is disabled (`FIREBASE_AUTH_ENABLED=false`), `app.py` swaps in a `DevUserMiddleware` that pins `request.state.user_id` to `GCLAW_USER_ID` (default `default_user`). Route handlers always read `user_id` off `request.state`.
- `dispatch/runner.py` — `AgentRunner` wrapping ADK's runner with session + memory + board services.

### Key design decisions

- **Hybrid architecture (Approach B)**: ADK agents handle tool use, Gemini integration, and context management. The custom orchestration layer owns the hierarchy, board, cron, and inter-agent communication.
- **Board-based communication**: Agents don't talk to each other directly — they write tasks and status to the kanban project board in Firestore. Anything that looks like direct agent-to-agent messaging is a bug.
- **Model routing is opt-in**: Controlled by `MODEL_ROUTING_ENABLED`. When off, every agent uses `GEMINI_FLASH_MODEL`. When on, the router is built from the Firestore model catalog when populated, otherwise from `_build_model_router` in `main.py`. Non-Gemini providers are wrapped with ADK's `LiteLlm` adapter inside the router, not at call sites.
- **Soul inheritance**: Base soul flows down the hierarchy. Each agent gets a domain-specific overlay. Dynamic specialists inherit from their parent manager.
- **Cross-user A2A** (roadmap): Planned for cross-user agent coordination. Not yet implemented — no A2A code path exists today. All current inter-agent coordination is board-mediated.

## GCP footprint

Everything — Cloud Run, Artifact Registry, Firestore, Firebase Auth, GCS buckets, secrets, service accounts — lives in **a single GCP project per deployment**. GClaw does not cross project boundaries. The project ID is supplied via the `_PROJECT_ID` Cloud Build substitution (or the `GCP_PROJECT_ID` env var at runtime); see `scripts/bootstrap-gcp.sh` for the one-time provisioning steps.

## Environment & settings

Configuration is centralized in `src/gclaw/settings.py` (pydantic-settings). `.env.example` is the source of truth for required variables. Notable toggles:
- `FIREBASE_AUTH_ENABLED` — off in local dev; flips the middleware choice in `api/app.py`.
- `MEMORY_ENABLED` + `MEMORY_BANK_REASONING_ENGINE_ID` — Memory Bank integration.
- `MODEL_ROUTING_ENABLED`, `GEMMA_ENDPOINT_ID`, `NEMOTRON_ENDPOINT_ID`, `OPENROUTER_API_KEY` — model routing.
- `GCLAW_CONFIG_DIR` (set to `/app` in the Dockerfile) — where `agents/` and `soul/` are loaded from.

## Skills

Skills are packaged capabilities that agents can execute — like playbooks. They live in `skills/<skill-name>/` with a `SKILL.md` entry point (or `instructions.md`) and supporting files. Built-in skills ship in `skills/` and are loaded into the Firestore `SkillRegistry` at startup. Highlights:

- **`gcp-audit/`** — GCP infrastructure audit against CIS benchmarks, security best practices, cost, and operational excellence. Intended to run under the Dev Manager.
- **`dev-pipeline/`**, **`code-review/`**, **`debug/`** — developer workflows.
- **`morning-briefing/`**, **`email-drafter/`** — workspace routines.
- **`content-quality-gate/`**, **`humanizer/`**, **`nano-banana-pro/`**, **`nano-banana-prompting/`**, **`ui-ux-designer/`** — content pipeline (driven by `content-mgr`). Brand-specific content skills live in your private overlay, not the public repo.
- **`devils-advocate/`**, **`handoff/`**, **`skill-audit/`** — meta/process skills.

Discovery and loading go through `src/gclaw/skill/` (`discovery.py`, `loader.py`, `registry.py`).
