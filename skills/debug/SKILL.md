---
name: debug
version: 1.0.0
description: Multi-agent competing hypotheses debugging. The dev-mgr spawns specialist investigators in parallel — each pursues a different theory — then converges on root cause. Use when a bug is non-obvious or a single investigator keeps anchoring on the wrong theory.
allowed-tools:
  - read_local_file
  - get_current_diff
  - list_failing_workflows
  - get_pr_diff
  - list_open_prs
  - context_write
  - context_read_latest
  - context_list
  - create_board_task
  - list_board_tasks
  - get_board_task
---

# Competing Hypotheses Debugging

Spawn multiple investigators to debug a problem in parallel. Each pursues a different theory, then they argue to convergence.

**Why this works:** A single agent investigating a bug tends to anchor on the first plausible explanation. Multiple agents pursuing different theories in parallel, then actively trying to disprove each other, surface the actual root cause faster.

## Arguments

`$ARGUMENTS` — Required: description of the bug, error message, failing behavior, or unexpected output.

If no arguments provided, ask what's being debugged.

---

## Phase 0: Setup

1. **Analyze the problem** from `$ARGUMENTS`. Read relevant files with `read_local_file`, check recent logs, pull the current working-tree diff with `get_current_diff` and any failing CI workflows with `list_failing_workflows`.

2. **Formulate 3 hypotheses** — each should be:
   - Plausible given the symptoms
   - Distinct from the others (different root causes, not variations of the same idea)
   - Testable (there's a way to prove or disprove it)

   Present the 3 hypotheses before proceeding. Get confirmation or adjustment from the user if the problem is ambiguous.

3. **Spawn 3 investigators** via `create_board_task` — one task per hypothesis, each tagged with `kind=debug-investigator`. The dev-mgr picks them up in parallel and writes results to the `debug/<run-id>` shared-context namespace.

---

## Phase 1: Investigation

Each investigator task description should contain:

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
5. Report back by calling `context_write(namespace="debug/<run-id>", ...)` with the verdict, key evidence (file paths, log lines, command outputs), and whether you now believe a different hypothesis is correct.

The goal is truth, not winning. Abandon your hypothesis the moment evidence disproves it.
```

Poll the investigator tasks with `get_board_task`. When all three reach `done`, read each verdict from the shared-context namespace with `context_list` + `context_read_latest`.

---

## Phase 2: Convergence

Collect all reports and assess:

- **Converged on one cause** → proceed to fix
- **Two theories still plausible** → run tiebreaker: spawn a 4th investigator task with both remaining hypotheses and ask it to design and run a specific test that would distinguish between them
- **All hypotheses disproved** → formulate 3 new hypotheses based on gathered evidence, run a second round (max 2 rounds total)

---

## Phase 3: Fix

Once root cause is identified, create board tasks for:

1. **Implement the fix** (minimal — fix the bug, nothing more)
2. **Verify the fix** and run related tests
3. **Check for regressions** or similar patterns elsewhere

---

## Phase 4: Report

Write the final report to shared-context namespace `debug/reports` with `context_write`:

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

## Notes for GClaw

- Investigators are standard ADK specialist agents spawned by the dev-mgr via board tasks — they are one-shot and don't share memory across runs, so each must get the full problem statement plus its hypothesis.
- If debugging a webhook or external integration, include the endpoint URL and relevant payload in the task description.
- If debugging a CI failure, include the failing workflow name (`list_failing_workflows`) and the PR diff (`get_pr_diff`) so investigators don't have to go hunt for them.
- The report in `debug/reports` is keyed by date and brief slug: pass `metadata_json='{"date":"YYYY-MM-DD","slug":"<brief>"}'` when calling `context_write`.
