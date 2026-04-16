---
name: debug
version: 1.0.0
description: Multi-agent competing hypotheses debugging. Spawns 3 subagents pursuing different theories in parallel, then converges on root cause. Use when a bug is non-obvious or a single investigator keeps anchoring on the wrong theory. Best used by Adlan for code bugs; also usable by Watson for integration/webhook failures.
allowed-tools:
  - Read
  - Write
  - Edit
  - exec
  - sessions_spawn
  - sessions_history
  - subagents
  - memory_search
  - memorybank_search
---

# Competing Hypotheses Debugging

Spawn multiple investigators to debug a problem in parallel. Each pursues a different theory, then they argue to convergence.

**Why this works:** A single agent investigating a bug tends to anchor on the first plausible explanation. Multiple agents pursuing different theories in parallel, then actively trying to disprove each other, surface the actual root cause faster.

## Arguments

`$ARGUMENTS` — Required: description of the bug, error message, failing behavior, or unexpected output.

If no arguments provided, ask what's being debugged.

---

## Phase 0: Setup

1. **Analyze the problem** from `$ARGUMENTS`. Read relevant files, check recent logs.

2. **Formulate 3 hypotheses** — each should be:
   - Plausible given the symptoms
   - Distinct from the others (different root causes, not variations of the same idea)
   - Testable (there's a way to prove or disprove it)

   Present the 3 hypotheses before proceeding. Get confirmation or adjustment from the user if the problem is ambiguous.

3. **Spawn 3 investigators** via `sessions_spawn(runtime="subagent", mode="run")`.

---

## Phase 1: Investigation

Send each investigator a task like:

```
You are INVESTIGATOR-{N} on a debugging team.

PROBLEM: {full problem description}

YOUR HYPOTHESIS: {hypothesis N}

OTHER HYPOTHESES BEING INVESTIGATED:
- Investigator 1: {hypothesis 1}
- Investigator 2: {hypothesis 2}
- Investigator 3: {hypothesis 3}

INSTRUCTIONS:
1. Gather evidence FOR your hypothesis. Read relevant files, check logs, run commands.
2. Also look for evidence AGAINST your hypothesis — be honest.
3. Check whether the problem can be reproduced.
4. Your verdict: CONFIRMED, DISPROVED, or INCONCLUSIVE
5. Report back with: verdict, key evidence (file paths, log lines, command outputs), and whether you now believe a different hypothesis is correct.

The goal is truth, not winning. Abandon your hypothesis the moment evidence disproves it.
```

Wait for all 3 to complete.

---

## Phase 2: Convergence

Collect all reports and assess:

- **Converged on one cause** → proceed to fix
- **Two theories still plausible** → run tiebreaker: spawn a 4th agent with both remaining hypotheses and ask it to design and run a specific test that would distinguish between them
- **All hypotheses disproved** → formulate 3 new hypotheses based on gathered evidence, run a second round (max 2 rounds total)

---

## Phase 3: Fix

Once root cause is identified:

1. Spawn one agent to implement the fix (minimal — fix the bug, nothing more)
2. Spawn a second to verify the fix and run related tests
3. Spawn a third to check for regressions or similar patterns elsewhere

---

## Phase 4: Report

```markdown
## Debug Report

### Problem
{original problem description}

### Root Cause
{1-2 sentences}

### Investigation Summary
| Hypothesis | Verdict | Key Evidence |
|------------|---------|--------------|
| {hypothesis 1} | CONFIRMED / DISPROVED | {1-line} |
| {hypothesis 2} | CONFIRMED / DISPROVED | {1-line} |
| {hypothesis 3} | CONFIRMED / DISPROVED | {1-line} |

### Fix Applied
{What was changed and where}

### Verification
- Tests pass: YES / NO
- Regression risk: low / medium / high
```

---

## Notes for OpenClaw

- Use `sessions_spawn(runtime="subagent", mode="run")` for investigators — they're one-shot
- If debugging a webhook or n8n flow, give investigators the webhook URL and relevant workflow JSON
- If debugging an Adlan build failure, give investigators the GitHub repo URL and the error log
- Log the debug report to `~/.openclaw/shared-context/debug/YYYY-MM-DD-{brief}.md`
