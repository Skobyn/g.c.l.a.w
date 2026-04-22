# GClaw

A multi-agent AI orchestration platform built on the Google stack.
GClaw uses the Google Agent Development Kit (ADK) for agent
execution and Gemini models for intelligence, with a custom
orchestration layer (hierarchical managers, kanban project board,
cron scheduler, session router) on top.

> **Status:** personal-use framework, evolving. Public-facing
> infrastructure is parameterized but the agent prompts and skills
> are still oriented around the original deployment. Treat this as a
> reference implementation to fork, not a turnkey product.

## What's in the box

Two first-class surfaces:

- **Backend** (`src/gclaw/`) — FastAPI app, ADK agents, Firestore
  persistence, Vertex AI Memory Bank for long-term recall.
- **Web client** (`web/`) — Next.js PWA with Firebase Auth, chat +
  voice UI (Gemini Live).

Plus seven domain-owning manager agents (Workspace, Dev, Home,
Comms, Research, Profile, Content), a tool registry, a skill
registry, and a Cloud Run deploy pipeline.

## Architecture (five layers)

1. **User** — PWA, voice (Gemini Live), Firebase Auth.
2. **Orchestration** — Agent hierarchy, kanban board, cron, session
   router. The differentiating layer.
3. **Agent** (ADK) — Specialist + manager agents bound to Gemini and
   tools.
4. **Memory** — Firestore for sessions/board/config; Vertex AI
   Memory Bank for long-term recall; `soul/*.md` for personality.
5. **Integration** — Tool modules in `src/gclaw/tools/` (Google
   Workspace, GitHub, comms, home, research, content).

Agents communicate through the **kanban board**, not directly. Any
direct agent-to-agent call is treated as a bug.

See [`CLAUDE.md`](./CLAUDE.md) for the deeper architectural tour
(written for AI assistants but doubles as a maintainer handbook).

## Quickstart (local, no GCP)

You can run the backend without Firebase, without Memory Bank, and
without Vertex AI by disabling the corresponding feature flags. ADC
credentials still need to point at *some* GCP project for Vertex
genai.

```bash
# Clone and install
git clone <your-fork-url>
cd gclaw
uv sync --extra dev

# Configure — copy .env.example and edit GCP_PROJECT_ID
cp .env.example .env
$EDITOR .env

# Run
uv run python -m gclaw.main           # :8080

# In another terminal:
cd web
cp .env.local.example .env.local      # set NEXT_PUBLIC_DEV_BYPASS_AUTH=true
npm install
npm run dev                            # :3000
```

Tests:

```bash
uv run pytest                          # backend
cd web && npm test                     # frontend
```

## Deploy (Cloud Run via Cloud Build)

The included `cloudbuild.yaml` deploys a backend + web pair to a
single GCP project. All deployment-specific values are Cloud Build
substitutions — defaults reflect the upstream maintainer's project,
override per fork:

```bash
gcloud builds submit \
  --project <your-project> \
  --config cloudbuild.yaml \
  --substitutions \
    _PROJECT_ID=<your-project>,\
_IMAGE=us-central1-docker.pkg.dev/<your-project>/gclaw/gclaw,\
_SERVICE_ACCOUNT=gclaw-run-sa@<your-project>.iam.gserviceaccount.com,\
_MEMORY_ENGINE_ID=<your-reasoning-engine-id>,\
_GWS_USER=<your-workspace-user>,\
_VPC_CONNECTOR=<your-connector-or-empty>
```

Before the first deploy you'll need to provision the GCP-side state
out-of-band: Firestore in Native mode, an Artifact Registry repo
named `gclaw`, a runtime service account with `aiplatform.user` +
`datastore.user` + `logging.logWriter` + `monitoring.metricWriter`,
a Vertex AI Memory Bank reasoning engine (if `MEMORY_ENABLED=true`),
and a GCS bucket for shared context. There's no bootstrap script
yet — see issue tracker for the planned `scripts/bootstrap-gcp.sh`.

## Skills

Skills are packaged capabilities that agents can execute — like
playbooks. They live in `skills/<skill-name>/` with a `SKILL.md`
entry point and supporting files. Built-in skills ship in `skills/`
and are loaded into the Firestore `SkillRegistry` at startup.

Highlights:

- **`gcp-audit/`** — Infra audit against CIS benchmarks.
- **`dev-pipeline/`**, **`code-review/`**, **`debug/`** — developer
  workflows.
- **`morning-briefing/`**, **`email-drafter/`** — workspace
  routines.
- **`content-quality-gate/`**, **`humanizer/`**,
  **`nano-banana-pro/`** — content pipeline (driven by
  `content-mgr`).

## Customizing for your own use

The manager agents (`agents/*.md`) and personality files
(`soul/*.md`) are hand-written for the upstream deployment. Forks
have two options:

1. **Edit in place** — change the agent prompts and soul files
   directly. Simpler if you don't plan to pull upstream changes
   often.
2. **Private overlay** — point `GCLAW_CONFIG_DIR` at a separate
   private repo containing your `agents/`, `soul/`, `user.md`, and
   personalized `crons/`. Lets you stay in sync with upstream for
   the framework while keeping your personality private.

Option 2 is what the upstream maintainer is moving toward.

## Documentation

- [`CLAUDE.md`](./CLAUDE.md) — full architecture, package map,
  design decisions.
- [`CONTRIBUTING.md`](./CONTRIBUTING.md) — dev setup, PR flow.
- [`SECURITY.md`](./SECURITY.md) — security disclosure policy.
- `docs/research/` — published architectural validations.

## License

[MIT](./LICENSE).
