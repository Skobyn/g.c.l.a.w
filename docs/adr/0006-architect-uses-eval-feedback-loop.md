# ADR-0006: architect-uses-eval feedback loop

**Status:** Proposed (2026-04-22) — implementation pending
**Context:** ADR-0002 ships the agent-architect; ADR-0005 ships the
eval framework. This ADR closes the loop: when the architect
generates a new agent, it must run an eval pass against a starter
evalset and report the score before the user approves registration.

Today's "is this new agent any good?" check is a vibes-only review
of the staged draft. That works for one or two agents; it doesn't
scale, and it doesn't catch tool-trajectory bugs that only show up
under realistic prompts.

## Decision

Add a third stage to the architect's pipeline (between **stage** and
**wait for approval**):

1. Clarify
2. Check for collisions
3. Draft body + soul
4. Stage draft to shared-context
5. **NEW**: Generate a starter evalset (3–5 cases inferred from the
   draft's stated capabilities + tools) and run `gclaw-eval` against
   the staged draft via an in-process ephemeral agent build.
6. Report scores alongside the draft. Score table is part of the
   approval-request payload.
7. Wait for approval (now informed)
8. Register

The architect does not gate registration on a score threshold by
default — that's the user's call. But it surfaces:

- `tool_trajectory_avg_score` — does the agent call the right tools?
- `final_response_match_v2` — does the agent answer plausibly?
- `hallucinations_v1` — does it stay grounded?

If any score is below 0.5 (configurable), the architect's report
includes a "this agent likely needs revision" warning before the
approval prompt.

## Architect tool additions

Two new tools alongside the architect's existing set:

| Tool | Purpose |
|---|---|
| `generate_starter_evalset(agent_name, body, tools)` | LLM-assisted: produces 3–5 plausible test cases based on the agent's described capabilities. Stored at `tests/eval/evalsets/<agent_name>.json`. |
| `run_eval_against_draft(agent_name, evalset_path, draft_body, draft_soul)` | Builds an ephemeral LlmAgent from the staged draft (without registering it permanently), runs the evalset, returns scores. Cleans up. |

The ephemeral build path is the trick. We need the factory to accept
a transient (body, soul, tools) tuple without persisting to Firestore.
Sketch:

```python
agent = factory.build_transient(
    agent_name=staged_name,
    body=draft_body,
    soul_overlay=draft_soul,
    tools=tools_resolver(declared_tools),
)
```

This is a small refactor in `factory.py` — extract the body+soul
loading from the persistent path into a parameterizable input.

## Starter evalset generation

The "generate me 5 plausible test cases for an agent that does X"
problem is itself a small LLM task. Prompt template:

```
You are writing test cases for a new agent.
Agent name: {name}
Agent body: {body}
Tools available: {tools}

Write 3–5 test cases. Each case has:
- input: a realistic user request the agent should handle
- expected_tool_uses: which tools you expect to be called and roughly
  what arguments
- expected_response: what a good answer looks like, as a rubric

Output as a JSON array matching the gclaw evalset schema.
```

Run via the Gemini orchestrator model (cheap, fast). Output is the
starter evalset — the user can edit before approving.

## Approval payload shape

After step 5, the architect's report-back to the orchestrator looks like:

```
DRAFT READY: <agent_name>

  Body:    <link to context-queue/agent-drafts/<name>>
  Soul:    <link>
  Model:   gemini-2.5-flash
  Tools:   web_search, fetch_url, board tools

  Eval (5 cases, judge=gemini-2.5-flash):
    tool_trajectory_avg_score:           0.92
    final_response_match_v2:             0.81
    hallucinations_v1:                   1.00 (clean)

  ⚠ All scores meet threshold; recommended: APPROVE.

Reply "approve" to register, "revise" with feedback, or
"add eval cases <description>" to extend the evalset.
```

When scores fail, the warning text becomes:

```
  ⚠ tool_trajectory_avg_score (0.42) below threshold (0.50).
    Likely cause: agent body doesn't constrain tool ordering tightly
    enough. Consider adding "always call X before Y" to the body, or
    relaxing the evalset's tool_uses to ANY_ORDER.
```

(That phrasing comes verbatim from the upstream eval skill's
"What to fix when scores fail" table — vendored as part of the
architect's prompt context.)

## Iteration

If the user replies "revise", the architect:

1. Re-drafts the body / soul per the user's feedback.
2. Re-runs the same evalset against the new draft.
3. Reports the score delta vs. the prior version.
4. Loops until "approve" or "abandon".

This is the agents-cli "eval-fix loop" pattern translated into
architect terms.

## What the user sees

For a "build me a finance-mgr that summarizes my Plaid balances"
request, the user would see:

1. Clarifying question (one only, if needed)
2. Draft + scores in the same turn
3. Approval prompt
4. Either "approve" → registered → live on next turn, OR
5. "revise" → loop with new scores

The architect does NOT silently iterate without showing the user.

## What we do NOT do (yet)

- **Auto-approve below a score threshold** — too risky early. Always
  surface the recommendation, let the user pull the trigger.
- **Generate evalsets for existing baseline agents** — separate
  workstream. Makes sense once the format is in use.
- **Run evals on every Architect call to update_agent_model.**
  Model swaps don't change the agent's contract; eval re-run is
  optional, not automatic.

## Dependencies

- ADR-0002 (agent-architect) — must ship first; this builds on it.
- ADR-0005 (evalset framework) — must ship first; the architect calls
  into the runner from ADR-0005.

## Open questions

- **Where does the evalset live for revised agents?** Per-agent file
  in `tests/eval/evalsets/<agent_name>.json`. New revisions append a
  case if the user adds one; otherwise the evalset is immutable
  per agent name.
- **Do generated evalsets get committed to the repo?** Yes — once
  the user approves the agent, both the agent override (Firestore)
  AND the evalset (file) get written. Future regression runs use
  the committed evalset.
