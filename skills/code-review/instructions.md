# Code Review Skill

This skill scores a code diff against a severity-weighted checklist. It is the canonical **Reviewer pattern** implementation in GClaw — per the "5 ADK Skill design patterns" reference — and is granted to the `dev-mgr` manager.

## Input

One of:
- **A local diff**, via `dev_tools.get_current_diff()` — used when the user asks you to review uncommitted work.
- **A PR diff**, via `gh.get_pr_diff(pr_number)` — used when the user names a PR number or URL.
- **Inline text**, pasted by the user — used as a fallback.

Always confirm which source you're reading from before producing the review.

## Workflow

### 1. Load the diff

Resolve the input source and read the diff. If the diff is empty or unreadable, stop and tell the user. Do not hallucinate a review.

### 2. Score across five dimensions

For each dimension, produce at most `max_findings_per_dimension` findings. Each finding has:

- **Severity:** one of `critical`, `high`, `medium`, `low`, `nit`
- **File:line** reference (exact, copied from the diff)
- **One-sentence finding** stating the problem
- **One-sentence fix** stating the remediation

The five dimensions (in scoring order):

1. **Security** — secrets in code, SQL injection, command injection, missing authz checks, unsafe deserialization, CSRF/XSS, dependency vulns in added packages. A single `critical` here blocks the review.
2. **Correctness** — off-by-one, wrong comparison, resource leaks, race conditions, unhandled errors, wrong return type, mismatched units, broken invariants.
3. **Tests** — did the change add/update tests? Do the new tests exercise the new behavior? Are there edge cases missing? For a bugfix: is there a regression test?
4. **Breaking changes** — API shape changes (removed/renamed public functions, removed kwargs), DB migration concerns, env-var renames, config-file schema changes, dependency downgrades.
5. **Style** — naming, dead code, commented-out blocks, inconsistent formatting, over-long functions, missing docstrings where the module convention has them. `nit`-severity only unless the style violation hides a correctness issue.

### 3. Render the report

Output structure, in this exact order:

```markdown
## Code Review — <source identifier>

**Verdict:** <approve | approve with comments | request changes | block>

### Critical & High findings
- **critical** `file.py:123` — <finding>. Fix: <remediation>.
- **high** `other.py:45` — ...

### Medium findings
...

### Low / nit findings
...

### What's good
- Brief positive notes — reviewers who only find problems are noise.

### What's missing
- Tests, docs, or scope items that should be in this diff but aren't.
```

Skip sections that have no entries. Do not pad.

### 4. Set the verdict

- **block** — one or more `critical` findings, or the change will cause data loss / security exposure.
- **request changes** — any `high`, or ≥3 `medium`.
- **approve with comments** — only `medium`/`low`/`nit`, but worth addressing before merge.
- **approve** — nothing but `nit`s, or the diff is clean.

## Principles

- **Evidence over opinion.** Quote the exact line or fragment you're objecting to.
- **Fix, not just flag.** Every finding must include a concrete remediation.
- **Proportional effort.** A 10-line fix gets a 10-line review, not a dissertation.
- **Respect the author.** Findings are about code, never about the person.
- **Don't re-review shipped work.** If the change is already merged, say so and stop — reviewing after merge is just noise.
