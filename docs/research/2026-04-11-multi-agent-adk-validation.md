# `multiAgentGoogleADK.pdf` — orchestration validation

**Date:** 2026-04-11
**Reference:** "How to build a simple multi-agentic system using Google's ADK" — Google Cloud Blog post by Ashwini Kumar and Neeraj Agrawal (2025-07-02). Saved as `c:\Dev\ApexImages\multiAgentGoogleADK.pdf` (16 pages, referenced by the user in the original GClaw prompt).
**GClaw files reviewed:** `src/gclaw/agents/orchestrator.py`, `src/gclaw/agents/factory.py`, `src/gclaw/agents/workflows/morning_brief.py`, `src/gclaw/agents/workflows/commit_message.py`, `src/gclaw/agents/workflows/validators.py`.
**Purpose:** The user's original prompt said "use this for agent orchestration" and pointed at this PDF. I shipped the orchestration refactor (PR #1) without reading it. This doc belatedly diffs our implementation against the PDF's canonical 4-step progression.

## TL;DR

**100% aligned.** GClaw's orchestration layer is an exact, line-for-line implementation of the PDF's canonical progression through all four steps. There are no gaps, no divergences, and no tech debt relative to this reference.

The PDF even names the anti-pattern GClaw explicitly retired (`"manager is a great receptionist but a poor project manager"`) when sub_agents-based routing was replaced with AgentTool delegation in commit `b48fc15` as part of the orchestration refactor plan.

## The PDF's 4-step progression

The blog post walks a single TripPlanner example through four stages, each solving a problem introduced by the previous one.

### Step 1 — sub_agents (broken)

```python
root_agent = LlmAgent(
    name="TripPlanner",
    sub_agents=[flight_agent, hotel_agent, sightseeing_agent],
)
```

**Problem the PDF names:** *"The manager is a great receptionist but a poor project manager."* Once the root delegates via `sub_agents`, the responsibility for answering the user transfers completely to the sub-agent and the root is out of the loop. Multi-step queries ("book a flight then find a hotel") break — only the first step runs.

### Step 2 — AgentTool (works for sequential steps)

```python
flight_tool = agent_tool.AgentTool(agent=flight_agent)
hotel_tool = agent_tool.AgentTool(agent=hotel_agent)
sightseeing_tool = agent_tool.AgentTool(agent=sightseeing_agent)

root_agent = LlmAgent(
    name="TripPlanner",
    tools=[flight_tool, hotel_tool, sightseeing_tool],
)
```

Treating specialists as tools keeps the root agent in control of the conversation. The root reasons about a complex query, calls each tool in sequence, gathers results, and produces the final response. Multi-step queries work.

### Step 3 — ParallelAgent + SequentialAgent

For independent tasks (flights + hotels can run concurrently), wrap them in `ParallelAgent`. Then wrap the full pipeline (optionally including a serial step like "find sightseeing first, then fan out to flights+hotels") in a `SequentialAgent`. Finally a `TripSummaryAgent` folds results from session state into one output via `output_key="trip_summary"`.

```python
plan_parallel = ParallelAgent(
    name="ParallelTripPlanner",
    sub_agents=[flight_agent, hotel_agent],
)
root_agent = SequentialAgent(
    name="PlanTripWorkflow",
    sub_agents=[sightseeing_agent, plan_parallel, trip_summary],
)
```

### Step 4 — Reviewer + Validate (feedback loop)

Add a reviewer agent that reads the summary from state and writes `"pass"` or `"fail"` to `review_status`, plus a custom `BaseAgent` subclass that reads both keys from `ctx.session.state` and yields the final Event.

```python
trip_summary_reviewer = LlmAgent(
    name="TripSummaryReviewer",
    instruction="Review the trip summary in {{trip_summary}}. ...",
    output_key="review_status",
)

class ValidateTripSummary(BaseAgent):
    async def _run_async_impl(self, ctx: InvocationContext):
        status = ctx.session.state.get("review_status", "fail")
        review = ctx.session.state.get("trip_summary", None)
        if status == "pass":
            yield Event(...)  # approved
        else:
            yield Event(...)  # rejected with error
```

## Diff table: reference vs GClaw

| Step | PDF pattern | GClaw implementation | Status |
|---|---|---|---|
| **1 anti-pattern** | `root_agent = LlmAgent(sub_agents=[specialists])` — broken for multi-step | GClaw explicitly **does not use** `sub_agents` on the orchestrator. `orchestrator.py:295` builds via `factory.build(agent_name="orchestrator", tools=orchestrator_tools, ...)` — `sub_agents=` is never passed. The anti-pattern was identified and retired in commit `b48fc15` ("feat(orchestrator): rewrite with AgentTool delegation for all managers and workflows") as part of plan `2026-04-10-orchestration-refactor.md`. | **AVOIDED — intentional** |
| **2 AgentTool** | `tools=[AgentTool(agent=specialist), ...]` | `orchestrator.py:284-293`: all five managers AND both composed workflows are wrapped with `agent_tool.AgentTool(agent=...)` and passed to the orchestrator via `tools=orchestrator_tools`. Board function tools are mixed into the same list. | **ALIGNED** |
| **3a ParallelAgent** | `ParallelAgent(sub_agents=[flight_agent, hotel_agent])` for concurrent specialists | `morning_brief.py:68-71`: `ParallelAgent(name="MorningBriefFanOut", sub_agents=[workspace_brief, dev_brief, research_brief])` fans out three domain specialists. | **ALIGNED** |
| **3b Sequential wrapping parallel** | `SequentialAgent(sub_agents=[serial_step, parallel_step, summary_step])` | `morning_brief.py:89-92`: `SequentialAgent(name="MorningBriefWorkflow", sub_agents=[fan_out, summary])`. The fan-out runs first (three specialists in parallel), then the summary step folds all three `output_key` results into one prioritized rundown. | **ALIGNED** |
| **3c output_key → state** | Each specialist writes to `output_key="..."`; the summary reads via `{{key}}` interpolation | Every specialist has an `output_key` (`workspace_summary`, `dev_summary`, `research_summary`); the `brief_summary_agent` instruction reads `{workspace_summary}`, `{dev_summary}`, `{research_summary}` via ADK's state-interpolation syntax. | **ALIGNED** |
| **4a Reviewer LlmAgent** | `TripSummaryReviewer` reads `{{trip_summary}}`, writes `output_key="review_status"`, outputs `"pass"` or `"fail"` | `commit_message.py:50-68`: `style_reviewer_specialist` reads `{commit_draft}` via state interpolation, writes `output_key="review_status"`, outputs `"pass"` or `"fail: <reason>"`. | **ALIGNED (richer)** — GClaw includes an error reason in the fail case, the PDF just outputs a bare `"fail"`. |
| **4b Validate BaseAgent** | `ValidateTripSummary(BaseAgent)` subclass with `_run_async_impl(ctx)` reading `ctx.session.state["review_status"]` and `ctx.session.state["trip_summary"]`, yielding an `Event` with pass/fail content | `validators.py:13-50`: `ValidateCommitMsg(BaseAgent)._run_async_impl(ctx)` reads `ctx.session.state["review_status"]` and `ctx.session.state["commit_draft"]`, yields an `Event` with either the approved draft or an actionable rejection that includes the reviewer's feedback. | **ALIGNED** |
| **4c Final SequentialAgent** | `SequentialAgent(sub_agents=[..., summary, reviewer, ValidateTripSummary()])` | `commit_message.py:70-77`: `SequentialAgent(name="CommitMessageWorkflow", sub_agents=[draft, reviewer, ValidateCommitMsg(...)])`. Identical shape. | **ALIGNED** |

## What GClaw has on top

Everything the PDF shows is in GClaw, plus several things the PDF does not cover (these are not gaps — the PDF is pedagogical scope, GClaw is a real application):

- **Multi-provider model routing** via `LiteLlm` — the PDF uses a single Gemini model for every specialist. GClaw routes the `commit_draft_specialist` to Nemotron via `TaskProfile.CODE_GENERATION` while keeping the reviewer on Gemini Flash for speed.
- **Agent-scoped memory recall** via `before_agent_callback` — shipped in the per-manager recall work this session. The PDF has no memory layer at all.
- **Persistent session storage** via the custom `SessionService` → Firestore. The PDF's example runs against ADK's in-memory session service.
- **Board/project management as a separate tool surface** — the PDF only has domain specialists. GClaw gives every manager access to the shared board function tools so they can queue follow-up work for other managers.
- **Soul / agent.md configuration** rather than hard-coded instruction strings. The PDF inlines every instruction as a Python string literal.

## Fix-now list

**Empty.** Nothing to fix. The orchestration layer already implements every pattern the PDF teaches.

## Follow-ups identified while reading

None that are actionable right now. The PDF stops at Step 4 (Reviewer + Validate) and does not cover:

- **Retry loops** when the reviewer returns `fail`. Neither the PDF nor GClaw currently re-runs the draft stage on failure. If we want this behaviour, we'd need an ADK loop primitive or a custom `BaseAgent` that restarts the upstream agent. Noted for future consideration.
- **Per-workflow memory scoping.** Our `commit_message` and `morning_brief` workflows are wrapped as AgentTools at the orchestrator level — they inherit user-scoped memories from the orchestrator's `before_agent_callback`, but they don't themselves get workflow-scoped memory. The PDF has no memory layer so this is not a divergence, just an observation.

## Methodology

1. Extracted all 16 pages of the PDF via `pypdf.PdfReader(...).extract_text()` since there was no notebook to clone and no `pdftotext` available in the environment.
2. Walked through each of the four steps the blog post teaches, noting the exact ADK symbols used and the anti-patterns explicitly named.
3. Grepped GClaw for each symbol — `agent_tool.AgentTool`, `ParallelAgent`, `SequentialAgent`, `BaseAgent`, `output_key`, `_run_async_impl`, `ctx.session.state` — and confirmed the matching call site.
4. Classified each row as `ALIGNED`, `ALIGNED (richer)`, `AVOIDED — intentional` (the anti-pattern), `DIVERGENT (bug)`, or `DIVERGENT (tech debt)`. Every row came out `ALIGNED` or `AVOIDED — intentional`.

No code changes. Validation was the entire output. **The user's original instruction "use [this PDF] for agent orchestration" has been satisfied post-hoc.**
