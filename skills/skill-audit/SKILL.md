---
name: skill-audit
version: 1.0.0
description: Analyze GClaw skill and capability usage logs and recommend which skills to keep, prune, or consolidate. Run after collecting a few weeks of usage data. Also audits agent capability usage — which tools, crons, and specialist agents are actually pulling weight versus dead weight.
allowed-tools:
  - context_write
  - context_read_latest
  - context_list
  - list_board_tasks
---

# Skill Audit

Analyze skill and capability usage to identify what's working, what's dead weight, and what should be pruned or improved.

## Prerequisites

GClaw records a usage event every time a skill is loaded into an agent's prompt (see `gclaw.usage.recorder.record_skill_use`). The events land in the `usage_events` Firestore collection and are surfaced through `/admin/usage` in the web UI.

This skill queries those events (indirectly, through the usage API) and produces a written audit. If `/admin/usage` shows fewer than 20 skill events total, report insufficient data and stop.

---

## Step 1: Check Data Sufficiency

Pull skill usage counts from the usage API (the dev-mgr's `usage_summary` tool when present, otherwise read the pre-aggregated summary from shared-context namespace `usage/skills/daily`).

If:
- No data → tell the user to exercise the system for a few weeks first, then stop
- Fewer than 20 skill events → not enough data yet, show current count and stop
- Less than 7 days of data → too early to draw conclusions, stop

---

## Step 2: Build Usage Report

From the usage data (fields: `timestamp`, `agent_name`, `skill_name`, `run_id`), compute:

1. **Frequency table** — skill name, total invocations, sorted descending
2. **Recency** — last used date for each skill
3. **Agent distribution** — which agents invoke which skills
4. **Trend** — skills used early but not recently (abandoned)

Present as a markdown table: Skill | Uses | Last Used | Agents | Trend

---

## Step 3: Categorize

- **ACTIVE** — used 3+ times in the last 30 days
- **OCCASIONAL** — used 1-2 times in the last 30 days
- **DORMANT** — not used in last 30 days but used before
- **NEVER USED** — registered but zero usage events

Also flag:
- **Duplicates** — skills that seem to overlap in purpose
- **Underperformers** — skills invoked but whose output was rarely acted on (cross-reference with board-task completion stats via `list_board_tasks`)

---

## Step 4: Cross-Reference Registered Skills

List every skill currently in the registry (the `/admin/skills` endpoint returns the full list). Compare against usage data. Flag anything registered but never invoked.

---

## Step 5: Recommendations

```
REMOVE (never used, low value):
  - skill-name

IMPROVE (used but not effective — output rarely acted on):
  - skill-name: {what's wrong with it}

KEEP (active/useful):
  - skill-name

PROMOTE (useful in one agent's allowlist, should be enabled for others):
  - skill-name → {target agents}
```

Wait for user approval before taking any action.

---

## Step 6: Execute Approved Changes

Skills are managed via `/admin/skills` (disable or delete) and `/admin/agents/<name>` (per-agent allowlist). Never hard-delete a skill before giving it an "archived" state — flip `enabled: false` on the skill record first, observe for a week, then delete.

Save the audit report itself to shared-context namespace `audits/skills` via `context_write` with `metadata_json='{"date":"YYYY-MM-DD"}'` so future audits can trend across runs.

---

## Bonus: Agent Capability Audit

Beyond skills, also audit:

**Cron jobs** — which crons have fired and delivered value vs. silent failures or ignored output. Check the `/admin/crons` run history.
**Agents** — which managers (dev-mgr, research-mgr, content-mgr, etc.) are actually being used vs. idle. Check the `/admin/heartbeat` dashboard and the `usage_events` collection.
**Webhooks** — which external integrations are active vs. stale. Check the `connections/` shared-context namespace and `/admin/context` for last-seen timestamps.

Data sources:
- `/admin/usage` for cost + frequency KPIs
- `/admin/heartbeat` for last known activity per agent
- `/admin/context` for output files with dates, grouped by namespace
