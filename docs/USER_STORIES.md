# GClaw Web — User Stories

Each story has: **Page**, **Persona** (Scott as the single user — this is a personal AI), **Acceptance criteria** (what should be true when it works), and **Currently known issues** (what's already on our radar). Tested with Chrome DevTools MCP via `gclaw-web-982188522148.us-central1.run.app`.

---

## 1. `/` (root) → /chat

**As Scott, when I open the app I want to land on the chat with the orchestrator ready.**

Acceptance:
- Root URL redirects (or routes) to `/chat`.
- Chat composer is focused and ready for input.
- Sidebar nav is visible with all sections numbered (`§ 01–14`).

---

## 2. `/chat`

**As Scott, I want a continuous chat with my orchestrator that delegates to managers and surfaces what they're doing.**

Acceptance:
- Past turns of the active session render in order with timestamps + author labels.
- Composer accepts a message → orchestrator responds inline.
- For HIGH-priority requests, the orchestrator invokes the manager AgentTool inline and the result lands in the same turn.
- For MEDIUM/LOW requests, the orchestrator queues a board task and tells me "queued for X".
- Inline binary delegation animation when a board task is created.
- BoardSummaryCard shows live counts per phase (queued/in_progress/needs_approval/done/failed).
- Composer supports voice (Gemini Live) when wired.
- Switching agent in the agent-roster sidebar pins my next message to that specific agent (chat agent-switcher).

Currently known issues:
- The orchestrator does NOT come back to chat on its own when a MEDIUM task completes. User has to check the board / task modal. Possible follow-up: post-completion notification into the chat session.

---

## 3. `/board`

**As Scott, I want a newspaper-style kanban that shows what every manager is doing right now.**

Acceptance:
- Seven columns: Backlog · Queued · In Progress · Needs Approval · Done · Failed · (Scheduled column from crons).
- Tasks show title, assignee, priority glyph, age stamp, optional one-line description.
- Drag-and-drop validates allowed transitions; invalid drops pulse the alert color.
- Approval cards show Approve / Reject with reason.
- "+ Task" / "+ Cron" buttons open creation modals.
- Click any card → TaskDetailsModal opens.
- DONE column collapses past N items with "Show all".

Currently known issues:
- Stale ghost DONE entries from before PR #55 (when the orchestrator was hallucinating completions). Leave for cleanup.

---

## 4. TaskDetailsModal (overlay on /board)

**As Scott, when I click a board task I want to see exactly what the assignee did.**

Acceptance:
- Modal shows task header (title, status, assignee, priority, ID).
- For IN_PROGRESS tasks: green "AGENT IS WORKING · POLLING EVERY 2s" banner.
- "✓ RESULT" section shows verbatim manager summary when DONE.
- "✗ FAILED" section with rejection note when FAILED.
- "AGENT ACTIVITY" timeline shows ONLY events that belong to this task — assignee-authored model/tool calls plus orchestrator delegation around `created_at`.
- Refresh button + ESC to close.

Currently known issues:
- Activity timeline still uses heuristic time-window filter (PR #57). Proper task↔event linkage via ContextVar-stamped `task_id` is a follow-up.

---

## 5. `/crons`

**As Scott, I want to see scheduled jobs and edit/disable them.**

Acceptance:
- Cron list with name, schedule, last fire, next fire, enabled toggle.
- Click → drawer with full config + edit/save/delete.
- "+ Cron" creates a new one.

---

## 6. `/memory`

**As Scott, I want to see what my agents have remembered about me and prune things that don't fit.**

Acceptance:
- Search box → semantic recall against Memory Bank.
- List recent memories per agent scope, with importance + topics.
- Delete individual memories.

---

## 7. `/admin/context`

**As Scott, I want a window into the shared context blackboard agents read/write.**

Acceptance:
- List of namespaces with last-updated stamp.
- Drill into a namespace → recent entries (text + image), authored agent, timestamp.

---

## 8. `/skills`

**As Scott, I want to see installed skills, their owners, and how they're invoked.**

Acceptance:
- Skill catalog grouped by domain.
- Each skill: name, description, owning agent(s), entry-point file.
- Edit/disable/delete from this view.

---

## 9. `/admin/agents`

**As Scott, I want to see every agent registered in the system and what model it runs.**

Acceptance:
- Full roster with model, soul overlay, heartbeat enabled? + cadence.
- Click agent → soul/agent.md preview, edit model.
- Add/remove agents (architect-driven).

---

## 10. `/admin/models`

**As Scott, I want a catalog of models I can route to and their per-agent assignments.**

Acceptance:
- Model catalog with provider, endpoint, $/1k tokens, capability tags.
- Per-agent primary + fallback chain editable.
- Bulk action to swap primary across all agents.

---

## 11. `/admin/heartbeat`

**As Scott, I want to see when each agent's heartbeat last fired and what it did.**

Acceptance:
- Per-agent panel: status badge (OK / OK_TOKEN / SENT / SKIPPED / FAILED), last preview text, "Trigger now" button.
- Heartbeat log with reasoning + tool calls + tasks created.
- Distinguish interval vs cron vs manual triggers.

Currently known issues:
- The "preview" text for OK_TOKEN ticks is the LLM's free-text ack — sometimes editorial ("X offline" etc.). Worth filtering to the sentinel only if it gets noisy.

---

## 12. `/admin/usage` (Observability)

**As Scott, I want a single pane showing token spend, agent activity, and per-author transcripts of recent sessions.**

Acceptance:
- KPI row: total cost, model calls, agent invocations, tool calls. Per-window selector (1h/24h/7d/30d).
- Hourly activity chart (stacked by kind).
- Top-N tables: models, agents, skills, tools.
- Recent Events table with kind filter chips and load-more.
- **Recent Transcripts** panel: lists recent sessions, click to expand → turn timeline → click turn → per-author text + tool calls (redacted).

Currently known issues (active bug):
- Recent Transcripts panel renders the empty state but the polling fetch never fires. Bundle has `listAgentRuns` defined but no call site — the hook's API fallback path doesn't reach the network. Need to find why the `useEffect` isn't running the fetch despite mounting.

---

## 13. `/admin/live`

**As Scott, I want a live cockpit for a specific in-flight session — current agent, model, token meter, cost ticker, turn timeline.**

Acceptance:
- Session selector (or `?session=` URL param).
- NowPlayingCard: which agent + model is active right now.
- ContextGauge: window utilization.
- TokenMeter: streaming tokens this session.
- CostTicker: $ accumulating.
- SessionTimeline: each turn with model, tokens, cost, status, click-to-expand → per-author transcript.

Currently known issues:
- Same Firestore-fallback story as /admin/usage if Firebase isn't configured client-side. PR #58 added API fallbacks for the same hooks.

---

## 14. `/connections`

**As Scott (planned), I want to see which other users are connected for cross-user A2A workflows.**

Acceptance:
- Inbound + outbound connection requests.
- Active connections list.
- Approve / decline / revoke.

(Note: the cross-user A2A spec exists; not all connections work end-to-end yet.)

---

## 15. `/admin/user` (User Profile)

**As Scott, I want to see what the system thinks it knows about me, and edit it.**

Acceptance:
- `user.md` rendered with markdown + edit toggle.
- Profile-mgr changes go through this page.

---

## 16. `/admin/tools`

**As Scott, I want a tool catalog with which agents can call which tools.**

Acceptance:
- Tool list with module, callable name, parameters.
- Per-agent allow/deny matrix.
- CRUD for catalog overrides.

---

## 17. `/login`, `/onboarding`

**As Scott, when I'm not logged in I get a login flow; first-time login routes me through onboarding to bootstrap profile-mgr.**

Acceptance:
- /login Firebase Auth (when enabled).
- Onboarding asks a short interview, persists answers via profile-mgr → `user.md`.
- Lands me at `/chat` after.

---

## Test Loop Procedure

For each story above:
1. Navigate via Chrome DevTools MCP.
2. Capture network + console.
3. Validate acceptance criteria against the rendered DOM and behavior.
4. If a bug surfaces: fix at the source, ship via PR, redeploy, retest.
5. Mark the story Pass / Fail + notes inline.

---

## Loop 1 results (2026-04-24, against currently deployed bundle)

| # | Page | Result | Notes |
|---|------|--------|-------|
| 1 | `/` → /chat | PASS | Root routes to /chat with composer focused |
| 2 | /chat | PASS | Sidebar shows all 14 sections, "Observability" at #10 |
| 3 | /board | PASS | All 7 columns + "+ Task" / "+ Cron" + 23 cards rendered |
| 4 | TaskDetailsModal | PASS | Filter scoped to assignee+delegation window (PR #57) |
| 5 | /crons | PASS | Cron list renders |
| 6 | /memory | PASS | Memory Explorer + search input |
| 7 | /admin/context | PASS | 8 namespaces visible with entry counts + ages |
| 8 | /skills | PASS | 16 skills registered |
| 9 | /admin/agents | PASS | 22 agents registered with model + heartbeat status |
| 10 | /admin/models | PASS | Provider list with per-provider model counts |
| 11 | /admin/heartbeat | PASS | Per-agent panels with previews. Note: previews still LLM-editorial because PR #56/#59 wiring landed but old logs remain. |
| 12 | /admin/usage | **FIX SHIPPED** | RecentTranscripts hook was passing `async () => null` to api-client → "Not authenticated" thrown → empty state. Fixed by using `useAuth().getIdToken`. |
| 13 | /admin/live | PASS-with-caveat | Renders no-session state; same null-token fix applies to its hooks (`useSessionTurns`, `useTurnMessages`) — included in same fix. |
| 14 | /connections | PASS | Form + empty inbound/outbound |
| 15 | /admin/user | PASS | About-the-User editor + timezone control |
| 16 | /admin/tools | PASS | Tool catalog with built-in tools |
| 17 | /login | PASS | Redirects to /chat in dev-bypass mode |

Net: 17/17 passing rendering, 1 functional bug found (#12) and fixed in this branch. Will re-run loop after deploy.
