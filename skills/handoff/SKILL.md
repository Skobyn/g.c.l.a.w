---
name: handoff
version: 1.0.0
description: Generate a structured handoff document to pass context between agents or sessions. Use when switching work between manager agents mid-task, resuming work in a new session, or archiving the state of a long-running project. Writes to shared-context and optionally stores a one-line summary in the Memory Bank.
allowed-tools:
  - context_read_latest
  - context_list
  - context_write
  - read_user_profile
---

# Context Handoff

Generate a structured prompt capturing current task context so it can be passed to another agent or session.

## Arguments

`$ARGUMENTS` — Optional: specific instructions about what to emphasize, or which agent is the target (e.g., "hand off to dev-mgr", "resume tomorrow", "pass to research-mgr").

---

## Instructions

Review the current conversation context, recent shared-context entries, and any relevant files. Synthesize a handoff document.

### Step 1: Generate the Handoff Document

```markdown
## Handoff: {brief title}
Generated: {YYYY-MM-DD HH:MM UTC}
From: {source agent or session}
To: {target agent or context}

### Background
{1-3 sentences on what was being worked on and why}

### What Was Done
- {completed work with specific file paths, URLs, board task IDs, or context entry IDs}

### Current State
{What is working, what is not, what is in progress}

### Key Decisions Made
- {decision}: {rationale}

### Remaining Work
- [ ] {specific actionable items}

### Important Context
- {gotchas, constraints, or patterns the next agent needs}
- {specific file paths, webhook URLs, secret names in Secret Manager, config files}
- {any blockers or dependencies on the user}

### Files / Resources to Read First
- {ordered list to get up to speed fast}
```

Keep it concise but complete enough that the receiving agent can continue without re-discovering context.

### Step 2: Save the Handoff

Call `context_write` with:
- `namespace="handoffs"` (or `"handoffs/<target-agent>"` when handing off to a specific manager)
- `content=<the handoff markdown>`
- `metadata_json='{"date":"YYYY-MM-DD","slug":"<brief-slug>","from":"<source>","to":"<target>"}'`

The returned entry ID is what you reference in any follow-up board task.

### Step 3: Store Summary in Memory Bank

If the Memory Bank is enabled (`MEMORY_ENABLED`), the heartbeat/consolidation service will pick up the new handoff entry on its next pass. For urgent handoffs, include a one-line summary in the metadata so it surfaces in memory searches without the full body.

---

## Target-Specific Notes

**Handing off to dev-mgr (builder):**
- Include: GitHub repo URL (if exists), GCP project, Cloud Run service name, tech stack, failing test or error log
- Use `list_open_prs` / `get_pr_diff` / `list_failing_workflows` to snapshot the dev state before writing the handoff

**Handing off to research-mgr (intel):**
- Include: research question, context/framing, what's already been found, output format desired
- research-mgr writes its findings to the `research/` shared-context namespace; reference any existing entries by ID

**Handing off to content-mgr (content):**
- Include: post angle, target audience, style constraints, any data/sources to incorporate
- All content must pass `content-quality-gate` and `humanizer` before reaching Postiz

**Handing off to the next session (resuming tomorrow):**
- Include: current project status, open blockers, what the user was waiting on, next recommended action
- Use namespace `"handoffs/resume"` so the morning-briefing cron can surface it at the start of the day
