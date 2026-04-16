---
name: skill-audit
version: 1.0.0
description: Analyze OpenClaw skill usage logs and recommend which skills to keep, prune, or consolidate. Run after collecting a few weeks of usage data. Also audits agent capability usage — which Watson tools, crons, and agents are actually pulling weight versus dead weight.
allowed-tools:
  - Read
  - Write
  - exec
  - memory_search
  - memorybank_search
---

# Skill Audit

Analyze skill and capability usage to identify what's working, what's dead weight, and what should be pruned or improved.

## Prerequisites

Requires the skill usage log at `~/.openclaw/workspace/logs/skill-usage.tsv`. If it doesn't exist, or has fewer than 20 entries, report insufficient data and stop.

The log is written to automatically when skills are invoked (see logging setup below).

---

## Step 1: Check Data Sufficiency

Read `~/.openclaw/workspace/logs/skill-usage.tsv`.

If:
- File doesn't exist → tell Scott to use the system for a few weeks first, then stop
- Fewer than 20 entries → not enough data yet, show current count and stop
- Less than 7 days of data → too early to draw conclusions, stop

---

## Step 2: Build Usage Report

From the TSV log (format: `timestamp\tagent\tskill\tcontext`), compute:

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
- **NEVER USED** — installed but zero log entries

Also flag:
- **Duplicates** — skills that seem to overlap in purpose
- **Underperformers** — skills invoked but whose output was rarely acted on (if context clues available)

---

## Step 4: Cross-Reference Installed Skills

List all skills in:
- `~/.openclaw/workspace/skills/`
- `~/.npm-global/lib/node_modules/openclaw/skills/`
- `~/.openclaw/workspace/*/skills/` (agent workspaces)

Compare against usage data. Flag anything installed but never invoked.

---

## Step 5: Recommendations

```
REMOVE (never used, low value):
  - skill-name

IMPROVE (used but not effective — output rarely acted on):
  - skill-name: {what's wrong with it}

KEEP (active/useful):
  - skill-name

PROMOTE (useful in one agent's workspace, should be global):
  - skill-name
```

Wait for Scott's approval before taking any action.

---

## Step 6: Execute Approved Changes

For removals: move to `~/.openclaw/workspace/skills/archived/` — don't delete.
For promotions: copy to `~/.openclaw/workspace/skills/`.

---

## Logging Setup

To enable automatic skill usage logging, add to each agent's cron or session startup:

When a skill is invoked, append to `~/.openclaw/workspace/logs/skill-usage.tsv`:
```
{ISO timestamp}\t{agent name}\t{skill name}\t{brief context}
```

Watson should log this automatically when loading a SKILL.md. Add this line to the top of any skill invocation:

```bash
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)\twatson\t{skill-name}\t{brief context}" >> ~/.openclaw/workspace/logs/skill-usage.tsv
```

---

## Bonus: Agent Capability Audit

Beyond skills, also audit:

**Cron jobs** — which crons have fired and delivered value vs. silent failures or ignored output
**Agents** — which agents (Argus, Adlan, Quill, Signal, etc.) are actually being used vs. spinning up and doing nothing
**Webhooks** — which n8n webhooks are active vs. stale

Data sources:
- `~/.openclaw/workspace/logs/` for any existing logs
- Heartbeat/memory for last known activity per agent
- `~/.openclaw/shared-context/` for output files with dates
