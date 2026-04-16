---
name: handoff
version: 1.0.0
description: Generate a structured handoff document to pass context to another agent or session. Use when switching agents mid-task, handing off a build from Watson to Adlan, passing research from Argus to Watson, or resuming work in a new session. Saves to shared-context and optionally stores a summary in the Memory Bank.
allowed-tools:
  - Read
  - Write
  - memory_search
  - memorybank_search
  - memorybank_correct
  - sessions_history
---

# Context Handoff

Generate a structured prompt capturing current task context so it can be passed to another agent or session.

## Arguments

`$ARGUMENTS` — Optional: specific instructions about what to emphasize, or which agent is the target (e.g., "hand off to Adlan", "resume tomorrow", "pass to Argus for research").

---

## Instructions

Review the current conversation context and any relevant files. Synthesize a handoff document.

### Step 1: Generate the Handoff Document

```markdown
## Handoff: {brief title}
Generated: {YYYY-MM-DD HH:MM UTC}
From: {source agent or session}
To: {target agent or context}

### Background
{1-3 sentences on what was being worked on and why}

### What Was Done
- {completed work with specific file paths, URLs, or identifiers}

### Current State
{What is working, what is not, what is in progress}

### Key Decisions Made
- {decision}: {rationale}

### Remaining Work
- [ ] {specific actionable items}

### Important Context
- {gotchas, constraints, or patterns the next agent needs}
- {specific file paths, webhook URLs, API keys locations, config files}
- {any blockers or dependencies on Scott}

### Files / Resources to Read First
- {ordered list to get up to speed fast}
```

Keep it concise but complete enough that the receiving agent can continue without re-discovering context.

### Step 2: Save the Handoff

Save to:
```
~/.openclaw/shared-context/handoffs/YYYY-MM-DD-{brief-slug}.md
```

### Step 3: Store Summary in Memory Bank

Use `memorybank_correct` or note for the session to save a 1-2 sentence summary of what was handed off, so it survives across sessions even if the file isn't read.

---

## Target-Specific Notes

**Handing off to Adlan (builder):**
- Include: GitHub repo URL (if exists), GCP project, Cloud Run service name, tech stack, failing test or error log
- Note: Adlan uses `sessions_spawn(runtime="acp")` and needs clear deliverables

**Handing off to Argus (intel):**
- Include: research question, context/framing, what's already been found, output format desired
- Note: Argus saves to `~/.openclaw/shared-context/research/`

**Handing off to Quill/Signal (content):**
- Include: post angle, target audience, style constraints, any data/sources to incorporate
- Note: All content must pass humanizer before Postiz

**Handing off to next session (Watson resuming tomorrow):**
- Include: current project status, open blockers, what Scott was waiting on, next recommended action
- Save a copy to `~/.openclaw/shared-context/queue/watson/resume-{date}.md`
