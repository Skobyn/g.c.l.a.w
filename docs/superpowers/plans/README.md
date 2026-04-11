# GClaw Implementation Plans

Implementation plans for GClaw. Each plan has a STATUS header at the top. This index is the truth table — the individual plan checkboxes are no longer reliable.

## Active (partial)

These plans have work remaining. See each file's STATUS header for what's done vs left.

| Plan | Focus |
|---|---|
| [2026-03-31-gclaw-memory-skills.md](2026-03-31-gclaw-memory-skills.md) | Memory Bank client, session management, skill system — skill wiring and session persistence still open |
| [2026-03-31-gclaw-web-auth.md](2026-03-31-gclaw-web-auth.md) | Firebase Auth + Next.js web app — backend done, frontend polish needed |
| [2026-03-31-gclaw-voice-dashboard.md](2026-03-31-gclaw-voice-dashboard.md) | Gemini Live voice, dashboards, admin views — scaffolded only |
| [2026-03-31-gclaw-a2a-onboarding.md](2026-03-31-gclaw-a2a-onboarding.md) | Cross-user connections + conversational onboarding — models done, flows left |

## Shipped

Moved to [`shipped/`](shipped/) once the work landed on `master`. Archive date is on each file's STATUS header.

| Plan | Shipped in |
|---|---|
| [shipped/2026-03-30-gclaw-foundation.md](shipped/2026-03-30-gclaw-foundation.md) | `0a69789..c49dea8` |
| [shipped/2026-03-30-gclaw-crons-heartbeat.md](shipped/2026-03-30-gclaw-crons-heartbeat.md) | `d3d439e..6c0886d` |
| [shipped/2026-04-03-multi-model-routing.md](shipped/2026-04-03-multi-model-routing.md) | `9d7e979..6be3a2b` via PR #1 `1edcb61` |
| [shipped/2026-04-10-orchestration-refactor.md](shipped/2026-04-10-orchestration-refactor.md) | `3d3e989..6be3a2b` via PR #1 `1edcb61` |
| [shipped/2026-04-04-multi-provider-routing.md](shipped/2026-04-04-multi-provider-routing.md) | Completed with architectural pivot — Tasks 1/3/4 deliberately reverted in `9c07595` and replaced by ADK `LiteLlm` |

## Notes on checkbox drift

The per-task `- [ ]` checkboxes inside each plan were never ticked during execution. Don't use them as a progress signal. The STATUS header at the top of each file is the single source of truth; if the header disagrees with the checkboxes, the header wins.
