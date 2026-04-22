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

---

## Prerequisites

### Local tools

| Tool | Why | Notes |
|---|---|---|
| `gcloud` CLI | All GCP provisioning + build submit | Authenticate with `gcloud auth login` and `gcloud auth application-default login` |
| `uv` | Python package manager | https://docs.astral.sh/uv/ |
| `docker` | Local container build; Cloud Build also needs it on the client for `gcloud builds submit` | |
| `node` 20+ & `npm` | Web client build + dev | |
| `firebase` CLI (optional) | Deploys `firestore.rules` + `firestore.indexes.json` | `npm install -g firebase-tools` |
| `gh` CLI (optional) | If you wire up GitHub Actions deploy | |

### GCP account requirements

- A GCP project you own (Owner or Project IAM Admin role).
- A billing account linked to that project (APIs won't enable
  otherwise; `bootstrap-gcp.sh` checks this upfront).
- Vertex AI available in your chosen region (default `us-central1`).

### External service accounts you'll want

Only `GEMINI_API_KEY` (or Vertex ADC via the runtime SA) is strictly
required to get chat working. Everything else is optional and
unlocks specific managers / skills:

| Provider | Why | Manager / skill that uses it |
|---|---|---|
| Google Cloud (Vertex AI) | Required — Gemini, Memory Bank | Orchestrator, all |
| Google Workspace domain-wide delegation | Workspace agent tools (Gmail, Calendar, Drive) | `workspace-mgr` |
| GitHub PAT (`gh` CLI) | Dev manager GitHub operations | `dev-mgr` |
| Anthropic API | Claude routing (optional) | `ModelRouter` |
| OpenAI API | OpenAI routing (optional) | `ModelRouter` |
| OpenRouter API | OSS model routing (optional) | `ModelRouter` |
| Perplexity API | Research tool (optional) | `research-mgr` |
| Postiz | Social-media scheduling | `content-mgr` |
| Slack | Comms bot | `comms-mgr` |
| Discord | Comms bot | `comms-mgr` |
| Anthropic Claude Code OAuth | Copilot-auth model routing (optional) | `ModelRouter` |

---

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

---

## First-time deploy (Cloud Run via Cloud Build)

Three scripts in `scripts/` cover the full path:

```bash
# 1. Provision GCP project state.  Idempotent — safe to re-run.
./scripts/bootstrap-gcp.sh <your-project> us-central1

# 2. Populate Secret Manager with API keys.
#    Dry-run plan first, then apply with --apply when ready.
./scripts/seed-secrets.sh <your-project>
./scripts/seed-secrets.sh <your-project> --apply --values ./my-secrets.env

# 3. Build + deploy.  Optionally create the heartbeat scheduler.
GWS_USER=you@yourdomain.com \
MEMORY_ENGINE_ID=<printed-by-bootstrap> \
HEARTBEAT_SCHEDULER=true \
./scripts/deploy.sh <your-project> us-central1
```

You can also drive `cloudbuild.yaml` directly via `gcloud builds
submit --substitutions ...` — `scripts/deploy.sh` is just a thin
wrapper that turns env vars into the substitution string.

### What `bootstrap-gcp.sh` provisions

**APIs enabled:**

| API | Used by |
|---|---|
| `aiplatform.googleapis.com` | Gemini, Memory Bank, optional Vertex model endpoints |
| `artifactregistry.googleapis.com` | Container images |
| `cloudbuild.googleapis.com` | Build + deploy pipeline |
| `cloudscheduler.googleapis.com` | Heartbeat loop (opt-in) |
| `datastore.googleapis.com` | Firestore in Datastore-mode compat layer |
| `firestore.googleapis.com` | Firestore Native mode |
| `iamcredentials.googleapis.com` | SA impersonation |
| `run.googleapis.com` | Cloud Run backend + web services |
| `secretmanager.googleapis.com` | API keys, OAuth tokens, GWS creds |
| `storage.googleapis.com` | Shared-context GCS bucket |

**Resources created:**

- **Firestore** — Native mode, default DB, in your chosen region.
  `firestore.rules` (deny-by-default access model) and
  `firestore.indexes.json` (composite indexes for board/session/usage
  queries) are applied if `firebase-tools` is installed.
- **Artifact Registry** Docker repo `gclaw` in your region.
- **Runtime SA** `gclaw-run-sa@<project>.iam.gserviceaccount.com`
  with these roles:
  - `roles/aiplatform.user` — Gemini + Memory Bank
  - `roles/datastore.user` — Firestore
  - `roles/logging.logWriter` + `roles/monitoring.metricWriter` — Cloud Run telemetry
  - `roles/secretmanager.secretAccessor` — API key bootstrap
  - `roles/storage.objectAdmin` — shared-context bucket
- **Cloud Build SA** (`<project-number>@cloudbuild.gserviceaccount.com`)
  gets:
  - `roles/run.admin` — deploy Cloud Run services
  - `roles/iam.serviceAccountUser` on the runtime SA — act as it
  - `roles/artifactregistry.writer` — push images
  - `roles/secretmanager.secretAccessor` — read the OTEL endpoint secret during deploy
- **GCS bucket** `gclaw-shared-context-<project>` — uniform access, in your region. Used by the shared-context blackboard service.
- **Vertex AI Memory Bank reasoning engine** (unless `--no-memory`). The script creates the engine via the Python SDK and prints the ID for the next deploy.

### What `seed-secrets.sh` writes

One Secret Manager resource per integration, all with labels
`app=gclaw, kind=api-key`. Secret names use the prefix from
`SECRET_NAME_PREFIX` (default `gclaw-`). Canonical list:

```
gclaw-gemini-api-key          GEMINI_API_KEY         (env-bootstrapped at startup)
gclaw-anthropic-api-key       ANTHROPIC_API_KEY
gclaw-openai-api-key          OPENAI_API_KEY
gclaw-openrouter-api-key      OPENROUTER_API_KEY
gclaw-github-copilot-token    GITHUB_COPILOT_TOKEN
gclaw-perplexity-api-key      PERPLEXITY_API_KEY
gclaw-slack-bot-token         SLACK_BOT_TOKEN
gclaw-slack-app-token         SLACK_APP_TOKEN
gclaw-discord-token           DISCORD_TOKEN
gclaw-postiz-token            POSTIZ_API_TOKEN       (env-bootstrapped)
gclaw-gh-token                GH_TOKEN               (env-bootstrapped)
gclaw-gws-credentials         GOOGLE_WORKSPACE_CREDENTIALS_FILE
                                                    (file-bootstrapped to /tmp/gws-credentials.json)
```

Secrets you don't have a value for are still created (with a
`REPLACE_ME` placeholder version) — rotate them later via the
admin UI at `/admin/secrets` or the seeder again.

### What `deploy.sh` does

1. If `OVERLAY` is set (default `$HOME/dev/gclaw-overlay`), rsyncs
   the overlay onto the working tree.
2. Runs `gcloud builds submit --config cloudbuild.yaml` with
   substitutions built from env vars.
3. Resets the working tree so overlay files don't accidentally get
   committed to the public framework.
4. If `HEARTBEAT_SCHEDULER=true`, creates (or updates) a Cloud
   Scheduler job `gclaw-heartbeat` that POSTs `/heartbeat` every 15
   minutes. Required for the proactive agent consciousness loop.

---

## Optional: additional infrastructure

Not required for the minimum-viable deploy; wire these up as you
need them.

### Firebase Auth

For real user auth (vs. `FIREBASE_AUTH_ENABLED=false` which pins a
single dev user), run the bootstrap script — it adds Firebase to
your existing GCP project, creates a web app, enables
email/password + anonymous sign-in, and emits the Firebase config:

```bash
./scripts/bootstrap-firebase.sh <your-project>
# writes web/.env.firebase — cat into web/.env.local for local dev,
# or pass as --build-args in web/cloudbuild.yaml for Cloud Run.
```

Then set `FIREBASE_AUTH_ENABLED=true` in your backend cloudbuild
substitutions + redeploy.

**Google sign-in is console-only** (OAuth consent screen + brand
review is partly manual). If you want it:

1. After `bootstrap-firebase.sh` completes, open
   `https://console.firebase.google.com/project/<your-project>/authentication/providers`
2. Enable "Google" → set the support email → save.

### Phoenix observability

Arize Phoenix runs as a second Cloud Run service and gives you a
trace/eval UI on top of the OpenInference spans gclaw already
ships. Data never leaves your project.

Three-step setup:

```bash
# 1. Provision Cloud SQL + VPC connector + SA + secrets.
./scripts/bootstrap-phoenix.sh <your-project> us-central1

# 2. Deploy Phoenix. The bootstrap script prints the exact command
#    with your project values pre-filled; typical form:
gcloud builds submit --project <your-project> \
  --config infra/phoenix/cloudbuild.yaml \
  --substitutions \
    _PROJECT_ID=<your-project>,\
_IMAGE=us-central1-docker.pkg.dev/<your-project>/gclaw/phoenix,\
_SERVICE_ACCOUNT=phoenix-run-sa@<your-project>.iam.gserviceaccount.com,\
_VPC_CONNECTOR=gclaw-connector

# 3. Wire the backend to Phoenix + redeploy.
PHOENIX_URL=$(gcloud run services describe phoenix \
  --region=us-central1 --project=<your-project> --format='value(status.url)')
printf '%s/v1/traces' "$PHOENIX_URL" | \
  gcloud secrets versions add otel-exporter-otlp-endpoint \
    --data-file=- --project=<your-project>
# Then redeploy the backend with OBSERVABILITY_ENABLED=true.
```

Cost: Cloud SQL `db_f1_micro` is ≈ $10/mo — set a budget alert. To
fully disable ingestion without tearing down Cloud SQL, flip
`OBSERVABILITY_ENABLED=false` on the backend; Cloud Trace keeps
receiving spans in-project at zero cost increase.

Phoenix is distributed under the **Elastic License 2.0** — self-host
for internal use is fine; redistribution / offering Phoenix as a
managed service to third parties is not. See
[`infra/phoenix/README.md`](./infra/phoenix/README.md) for rollback
commands and deeper deployment reference.

### Vertex AI model endpoints (Gemma 4, Nemotron)

Only needed if `MODEL_ROUTING_ENABLED=true` and you want non-Gemini
providers via Vertex. See
[`infra/vertex-models/README.md`](./infra/vertex-models/README.md)
and the deploy scripts in the same directory.

### GitHub Actions auto-deploy (Workload Identity Federation)

`.github/workflows/deploy.yml` supports automatic deploys from
`master` via WIF. The setup commands are in the file's comment
header — one-time `gcloud iam workload-identity-pools create …`
sequence.

---

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
(`soul/*.md`) in the public repo are generic templates. Forks have
two options:

1. **Edit in place** — change the agent prompts and soul files
   directly. Simpler if you don't plan to pull upstream changes
   often.
2. **Private overlay** — put your personalized `agents/`, `soul/`,
   `user.md`, `crons/`, brand-specific skills, and `.env` in a
   separate private repo. `scripts/deploy.sh` rsyncs the overlay
   onto the framework at build time. Lets you stay in sync with
   upstream while keeping your voice private. Full guide in
   [`docs/OVERLAY.md`](./docs/OVERLAY.md).

## Documentation

- [`CLAUDE.md`](./CLAUDE.md) — full architecture, package map,
  design decisions.
- [`CONTRIBUTING.md`](./CONTRIBUTING.md) — dev setup, PR flow.
- [`SECURITY.md`](./SECURITY.md) — security disclosure policy.
- [`docs/OVERLAY.md`](./docs/OVERLAY.md) — private overlay pattern.
- [`docs/SECRETS_MIGRATION.md`](./docs/SECRETS_MIGRATION.md) — Secret
  Manager name-prefix migration.

## License

[MIT](./LICENSE).
