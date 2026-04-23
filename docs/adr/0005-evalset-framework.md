# ADR-0005: Evalset framework + `gclaw eval` CLI

**Status:** Proposed (2026-04-22) — implementation pending
**Context:** gclaw has `src/gclaw/eval/vertex_scoring_service.py` —
a thin wrapper around Vertex Gen AI Eval that scores a single
response. There is no:

- Evalset format (collection of test cases)
- Trajectory scoring (was the right tool called in the right order?)
- Diff-two-runs CLI (regression detection)
- Multi-turn conversation simulation
- Rubric-based scoring (LLM-as-judge with custom criteria)

`agents-cli` has all of these as `agents-cli eval run`. We adopt their
**format and metric set** (so evalsets are interchangeable) and
build a thin in-gclaw runner that doesn't require their scaffold layout.

## Decision

1. **Evalset JSON schema**: 1:1 with agents-cli's
   (`tests/eval/evalsets/<name>.json`). Each case:

```json
{
  "case_id": "research-mgr-finds-time",
  "input": "What time is sunrise in Chicago tomorrow?",
  "agent_name": "research-mgr",
  "expected_tool_uses": [
    {"name": "web_search", "args_match": {"query": ".*sunrise.*chicago.*"}}
  ],
  "expected_response": {
    "match_type": "rubric_based_final_response_quality_v1",
    "rubric": "The response includes a specific time and a source URL."
  }
}
```

2. **Metric set** (subset of agents-cli's that maps cleanly):
   - `tool_trajectory_avg_score` — exact / in-order / any-order match
   - `response_match_score` — lexical
   - `final_response_match_v2` — semantic (judge model)
   - `rubric_based_final_response_quality_v1` — LLM-as-judge with
     a free-form rubric
   - `rubric_based_tool_use_quality_v1` — judge-as-tool-reviewer
   - `hallucinations_v1` — fact-check vs. tool output
   - `safety_v1` — refuse-checks

3. **Runner** at `src/gclaw/eval/runner.py`:
   - Loads evalset JSON from `tests/eval/evalsets/`
   - For each case: spins up an in-process `AgentRunner` against the
     specified agent, captures the trajectory + response
   - Scores via the metric set; LLM judges use the orchestrator's
     model (Gemini 2.5) by default, configurable per-evalset
   - Writes results to `tests/eval/results/<timestamp>.json`

4. **CLI** at `src/gclaw/cli/eval.py`, exposed via the existing
   pyproject `[project.scripts]` block as `gclaw-eval`:
   ```bash
   gclaw-eval run --evalset tests/eval/evalsets/research-mgr.json
   gclaw-eval run --all
   gclaw-eval compare baseline.json candidate.json
   ```

## Why this and not "just use agents-cli eval"

`agents-cli eval run` requires their scaffold layout (`app/agent.py`,
`tests/eval/`, `tests/eval/eval_config.json`). Trying to retrofit that
on top of gclaw's `agents/*.md` + factory-built LlmAgents would be
worse than building our own runner.

The KEY thing we preserve is **format compatibility**. Our evalset
JSON is the same as theirs; if we ever decide to migrate or run their
CLI as a sanity check, no conversion needed.

The runner is small — a few hundred lines wrapping the existing
`AgentRunner`. The metrics are mostly LLM-as-judge calls that don't
care what framework owns the agent.

## Where evalsets live

```
tests/eval/
  evalsets/
    research-mgr.json          # one file per agent under test
    workspace-mgr.json
    orchestrator-routing.json  # multi-turn cases for the root
  results/
    2026-04-22T22-30-00.json   # written by `gclaw-eval run`
  rubrics/
    response-quality.md        # shared rubrics referenced by evalsets
```

`tests/eval/evalsets/` ships in the repo. `tests/eval/results/` is
gitignored — results are local to a run.

## CI integration (later)

Once we have evalsets for the core agents, GitHub Actions runs
`gclaw-eval run --all --threshold .85` on every PR that touches
`agents/` or `src/gclaw/agents/`. Fails the build on regression.

Out of scope for the initial PR — first we need evalsets to exist.

## What we explicitly do NOT do

- **Don't fork or vendor agents-cli's eval implementation.** Their
  code is closed (distributed as a wheel). We re-implement against
  the same format.
- **Don't run evals against the deployed Cloud Run service.** Eval
  runs construct an `AgentRunner` directly — no HTTP, no auth, no
  deploy dependency. CI can run them in a unit-test container.

## Open questions

- **Judge model** — Gemini 2.5 by default. Should we let the evalset
  declare a different judge per case (e.g., Claude Sonnet for higher-
  quality rubric scoring on hard cases)? Probably yes; defer to the
  implementation PR.
- **Cost** — judge calls aren't free. Cap iterations at N per CI run;
  cache judge verdicts on (input, response, rubric) tuples.

## Dependencies

- ADR-0003 / 0004 (analytics + prompt log) are NOT prerequisites.
  They're complementary — analytics rows from ADR-0003 can be
  replayed as evalset cases later.
- ADR-0006 (architect-uses-eval) depends on this. Architect needs a
  starter evalset to score generated agents against.
