# ADR-0001: Selective adoption of `google/agents-cli`

**Status:** Accepted (2026-04-22)
**Context:** Investigation of `google/agents-cli` after a day of debugging
where regional Vertex quota, double-Bearer Anthropic headers, and a
Vertex-routed Gemini-3 preview each broke production in turn.

## Decision

We adopt `google/agents-cli` **selectively**. Specifically:

- **Vendor** their `google-agents-cli-adk-code` skill into
  `skills/adk-patterns/` as authoritative reference material for any
  agent that writes ADK code (today: `agent-architect`).
- **Mirror** their schemas where it's cheap — evalset JSON,
  BigQuery Agent Analytics event shape, prompt-response log layout —
  so we stay format-compatible and could later run `agents-cli eval`
  or analytics tooling against gclaw without a migration.
- **Do not** rebuild gclaw's agent system on top of their scaffold.
- **Do not** install `agents-cli` as a runtime binary inside the gclaw
  Docker image. Skills travel as content; the CLI does not travel with
  us.

## Rationale

`agents-cli` is built to scaffold and ship **single-agent products** on
Gemini Enterprise Agent Platform. It assumes one agent per project,
deployed as one Cloud Run / Agent Runtime / GKE service, with one
session backend, one observability stack, one eval suite.

gclaw is a **multi-agent platform**. It has:

- A root orchestrator that delegates to seven managers
- Managers that route to short-lived specialists
- A kanban board for async hand-offs
- A heartbeat scheduler waking agents on independent intervals
- A soul-overlay personality system layered on agent bodies
- A web UI talking to FastAPI routers (`/chat`, `/board`, `/api/events`)
- Multi-provider model routing through LiteLLM (Anthropic OAuth,
  GitHub Copilot, Gemini public API, Vertex, custom OpenAI-compatible)
- Standalone-agent CRUD via the admin UI without redeploys

None of that exists in `agents-cli` because their target is different.
A "consistency-driven" rebuild on top of their scaffold would mean
inventing the manager/board/heartbeat patterns *on top of* their
single-agent scaffold — i.e., the same architecture we have now,
rewritten in their layout, with weeks of risk and zero capability gain.

The pieces of `agents-cli` worth adopting are **format-level** (skill
shape, evalset schema, BigQuery analytics columns), not
**framework-level** (their CLI, their AdkApp wrapper, their
agent-as-code idiom). Adopting formats keeps us interoperable; adopting
their framework would force a regression.

## What we adopt and where

| Asset from `agents-cli` | Where it lives in gclaw | Status |
|---|---|---|
| `adk-code` skill (ADK Python API reference) | `skills/adk-patterns/` (vendored, Apache-2.0) | **Done** in this PR |
| Skill format (YAML frontmatter + body) | gclaw's `SKILL.md` parser already accepts it | **Done** (existing) |
| BigQuery Agent Analytics schema | `src/gclaw/observability/bq_analytics.py` (planned) | **ADR-0003** |
| Prompt-response log shape | `src/gclaw/observability/prompt_log.py` (planned) | **ADR-0004** |
| Evalset JSON schema + metric set | `src/gclaw/eval/evalset.py` + `gclaw eval` CLI | **ADR-0005** |

## What we explicitly reject

| Pattern | Why not |
|---|---|
| Migrating to Agent Runtime (their managed Vertex deploy) | Loses multi-agent in-process model, web UI, custom routes |
| Rebuilding agents in Python (`Agent(name=, instruction=, tools=...)` calls) | Loses markdown editability, soul overlays, runtime CRUD via admin UI |
| `agents-cli` CLI in the runtime Docker image | Adds dependency we don't use; their commands assume scaffold layout we don't have |
| Their Terraform modules | Worth revisiting later; current bash bootstrap works and the migration cost is non-trivial |

## Consequences

**Good:**

- Future agent-architect-generated code follows Google's authoritative
  ADK patterns (because the skill is loaded into its prompt).
- We stay on a known-good upgrade path: when ADK changes, vendoring a
  newer skill version is a one-file refresh.
- BigQuery analytics + evalsets, when added, are queryable by anyone
  familiar with the standard schema. Hiring a contractor doesn't
  require teaching them gclaw-specific event shapes.

**Bad / accepted trade-offs:**

- We have to maintain the architect / observability / eval glue
  ourselves. ADR-0002 through 0006 spell out the shape.
- We're vendoring 1.6k lines of upstream markdown into the repo. That's
  a maintenance cost (re-vendor on upstream updates). Worth it for the
  pattern stability.
- We do NOT get one-command deploy via `agents-cli deploy`. We keep
  using `cloudbuild.yaml` + GitHub Actions.

## See also

- ADR-0002 — agent-architect for in-process agent creation
- ADR-0003 — BigQuery Agent Analytics adoption
- ADR-0004 — Prompt-response logging to GCS
- ADR-0005 — Evalset framework + `gclaw eval` CLI
- ADR-0006 — Architect-uses-eval feedback loop
- Upstream: https://github.com/google/agents-cli (Apache-2.0)
