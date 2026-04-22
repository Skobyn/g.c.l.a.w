# GClaw — Personal AI Agent Platform on Google Stack

**Date:** 2026-03-30
**Status:** Design approved, pending implementation plan

## Overview

GClaw is a personal AI assistant platform built entirely on the Google ecosystem. It combines a multi-agent hierarchy with a kanban-based project board, persistent memory, scheduled automation (crons + heartbeat), and an extensible skill system. The agent is proactive — not just a chatbot waiting for input — with a consciousness loop (heartbeat) that wakes it periodically to reason about what needs attention.

Architecture — soul, tools, agents, crons, heartbeat, skills — built on Google's stack: ADK, Gemini, Vertex AI Memory Bank, Firestore, Cloud Run, A2A protocol, and Firebase.

## Architecture — Five Layers

### 1. User Layer

Three interaction modes:

- **Text chat** — primary interface via a PWA web app (Next.js, Tailwind CSS, Firebase Hosting). Supports rich responses: markdown, images, cards, action buttons.
- **Voice** — Gemini Live API via WebSocket for real-time voice conversation. Browser MediaRecorder for audio capture.
- **Notifications** — Firebase Cloud Messaging (FCM) for push notifications from heartbeat, crons, and agent escalations. Actionable — tap to respond.

Five web app views:

- **Chat View** — conversational interface with voice toggle, file attachments, inline image generation.
- **Board View** — kanban board showing all tasks across agents. Drag to reorder, approve escalations, cancel tasks, manually create tasks. Real-time via Firestore listeners. Filter by agent, priority, source.
- **Agent Dashboard** — agent status, recent activity, health. Configure settings, edit soul overlays, manage tool grants and skill assignments. Heartbeat logs.
- **Skills & Crons** — browse, install, configure, and create skills. Manage cron schedules, view run history.
- **Memory Explorer** — search, browse, and manage long-term memories. View by topic, edit/delete individual memories. Soul file editor for direct overrides.

### 2. Orchestration Layer (Custom)

The brain of the system. Manages agent hierarchy, routes tasks, runs the kanban project board, executes crons, and handles inter-agent communication via the board.

This layer is what makes GClaw unique — it sits above ADK and owns the coordination logic.

### 3. Agent Layer (ADK)

Gemini-powered agents built with Google's Agent Development Kit. Each agent has tools bound to it and operates within the hierarchy defined by the orchestration layer.

### 4. Memory Layer

Firestore for real-time state (sessions, board, config). Vertex AI Memory Bank for long-term recall. Session compaction bridges the two.

### 5. Integration Layer

Extensible tool system. Each integration is a tool module that agents can be granted access to: Google Workspace (Gmail, Calendar, Drive, Docs), GitHub, Smart Home/IoT, Communication (Slack, Discord, SMS), Web Research, Image Generation (Gemini Image Pro).

## Agent Model — Every Agent Has a Soul

### Agent Anatomy

Every agent (orchestrator, managers, specialists) has two halves:

**`agent.md`** — What it does:
- Role definition and responsibilities
- Tool grants (which tools it can use)
- Authority level (can it spawn sub-agents?)
- Escalation rules
- Domain boundaries

**`soul.md`** — How it behaves for this user:
- User's communication style preferences
- User context relevant to this domain
- Tone, verbosity, formality level
- User-specific rules and preferences
- Evolved through conversation over time

**System prompt = agent.md + soul.md + injected memories from Vertex AI Memory Bank**

### Hierarchy — Tiered with Dynamic Spawning

**Root Orchestrator:**
- Single entry point for all user interaction
- Loaded with the user's base soul personality profile
- Intent classification — understand what the user wants and route to the right manager
- Session continuity — maintain conversational context, inject relevant memories
- Personality — respond in the user's preferred style (built during onboarding)
- Escalation handler — when managers need clarification or approval, the orchestrator mediates

**Managers (Fixed Tier):**
- Pre-configured agents that own a domain: Workspace, Dev, Home, Comms, Research
- Each has an `agent.md` defining role, capabilities, tool grants
- Authority to spawn specialist agents for sub-tasks
- Read/write access to the project board for their domain
- Can create tasks for other managers (via the board, not directly)

**Specialists (Dynamic Tier):**
- Spawned by managers on demand
- Lightweight, single-purpose ADK agents
- Bound to specific tools (e.g., Gmail Agent only has Gmail tools)
- Short-lived — complete task, report back to manager, terminate
- Can also be spawned dynamically when a task requires a novel combination of tools
- Results posted to the project board

**Routing example:**
User says: "Schedule a meeting with Sarah about the Q2 roadmap and draft an agenda from our last project notes."

1. **Orchestrator** classifies intent → multi-domain (Workspace + Research)
2. **Orchestrator** creates two tasks on the project board: "Draft agenda from project notes" → Research Mgr, "Schedule meeting with Sarah" → Workspace Mgr
3. **Research Mgr** spawns a specialist to search Drive/notes, produces agenda draft, posts to board
4. **Workspace Mgr** picks up agenda from board, spawns Calendar Agent to schedule + Gmail Agent to send invite with agenda
5. **Orchestrator** sees both tasks completed, reports back to user

### Soul Inheritance and Specialization

- A base `soul/base.md` captures the user's global preferences (communication style, personality, general rules)
- Each agent has a domain-specific soul overlay with user context relevant to its role
- The Gmail Agent doesn't need to know your coding style — it needs your email tone and sign-off preferences
- During onboarding, the orchestrator interviews the user to build the initial soul profile
- Over time, each agent refines its domain-specific soul based on user feedback and corrections — stored to Vertex AI Memory Bank and synced to soul overlays
- When a manager spawns a dynamic specialist, it passes down the base soul + relevant domain soul context

## Project Board — Kanban & Inter-Agent Communication

### Kanban Columns

Backlog → Queued → In Progress → Needs Approval → Done

### Task Schema (Firestore)

```json
{
  "id": "task_abc123",
  "title": "Schedule meeting re: Q2 agenda",
  "description": "Book 30min with Sarah, attach agenda",
  "status": "queued | in_progress | needs_approval | done | failed",
  "priority": "high | medium | low",
  "source": {
    "type": "user | agent | cron",
    "origin": "research-mgr"
  },
  "assignee": "workspace-mgr",
  "dependencies": ["task_xyz789"],
  "attachments": [
    { "type": "artifact", "ref": "artifacts/draft_agenda.md" }
  ],
  "requires_approval": true,
  "cron": {
    "schedule": "0 8 * * MON",
    "mode": "auto | todo"
  },
  "result": {
    "summary": "Meeting booked for Tue 2pm",
    "artifacts": ["artifacts/invite.ics"]
  },
  "created_at": "2026-03-30T08:00:00Z",
  "updated_at": "2026-03-30T08:02:15Z"
}
```

### Three Ways Tasks Get Created

1. **User → Board** — User says something, orchestrator creates task(s). User can also directly add/reorder tasks through the web UI.
2. **Agent → Board (inter-agent communication)** — An agent creates a task assigned to another agent. Data passed via `attachments`. The receiving agent picks it up from the board — no direct calls.
3. **Cron → Board** — Scheduled jobs with two modes:
   - `mode: "auto"` — task created and immediately picked up by the assigned agent. Fully automated.
   - `mode: "todo"` — task created in backlog for the agent to pick up when it has capacity, or for the user to prioritize.

### Board as Communication Protocol

Agents never call each other directly. All inter-agent communication goes through the board. This provides:

- **Visibility** — the user can see everything agents are doing, reorder, approve, or cancel
- **Audit trail** — every task has a source, assignee, timestamps, and result
- **Decoupling** — agents don't need to know about each other, just the board
- **Resilience** — if an agent fails, the task stays on the board for retry or reassignment
- **Real-time** — agents subscribe to board changes via Firestore listeners

## Heartbeat — The Consciousness Loop

The heartbeat is not a health monitor. It is the orchestrator's wake cycle — the thing that makes the agent proactive rather than reactive.

### Heartbeat Cycle

1. **Wake Up** — Cloud Scheduler triggers a Cloud Function at a configurable interval (default: every 15 min). The function invokes the orchestrator's heartbeat cycle via Cloud Run.

2. **Gather Context** — The orchestrator assembles its world state:
   - Time and date — what's relevant now
   - Memories — retrieve from Vertex AI Memory Bank (reminders, pending commitments)
   - Kanban scan — outstanding tasks, stale items, failed tasks needing retry
   - Cron check — any cron-generated todos sitting in backlog
   - User calendar — upcoming meetings, deadlines
   - Unread notifications — emails, messages, PR reviews

3. **Reason and Decide** — With full context, the orchestrator decides what to do:
   - Proactive actions — "You have a meeting in 30 min, want me to pull the agenda?"
   - Task triage — pick up queued items, delegate to managers
   - Reminders — surface things the user asked to be reminded about
   - Housekeeping — retry failed tasks, clean up stale items
   - Nothing — if all is quiet, go back to sleep

4. **Act or Notify** — Depending on what it found:
   - Auto-execute — create tasks on the board, delegate to managers
   - Notify user — push notification with summary and suggested actions
   - Silent — log the heartbeat, go back to sleep

5. **Sleep** — Cloud Function exits. Cloud Scheduler fires again at next interval. Zero cost between beats.

### Heartbeat vs Crons

| | Heartbeat | Crons |
|---|---|---|
| Purpose | Orchestrator's wake cycle | User-defined scheduled jobs |
| Behavior | Gathers full context, reasons about what to do | Executes a specific configured task |
| Initiative | Proactive — can initiate actions the user didn't ask for | Reactive — execute what was configured |
| Scope | Scans board, calendar, notifications, memories | Creates tasks on the board |
| Frequency | Every 15 min (configurable) | User-defined schedules |

## Skills — The Capability Layer

Skills are modular, composable, user-configurable capabilities that give agents compound workflows with judgment — not just atomic API calls.

### Skills vs Tools

| | Tools | Skills |
|---|---|---|
| Scope | Atomic operations | Compound workflows with judgment |
| Example | "Send an email" | "Draft a professional email matching my tone" |
| Intelligence | None — API wrappers | Instructions + examples + config + tool orchestration |
| Binding | Bound to agents at config time | Discovered dynamically by context |
| Location | `tools/` | `skills/` |

### Skill Schema

```json
{
  "name": "email-drafter",
  "description": "Draft professional emails matching user's tone",
  "version": "1.2.0",
  "trigger": {
    "mode": "auto | manual | both",
    "contexts": ["composing email", "replying to thread"],
    "command": "/draft-email"
  },
  "config": {
    "formality": "professional",
    "max_length": 500,
    "always_cc": ["assistant@company.com"]
  },
  "tools_required": ["gmail", "contacts"],
  "agents_granted": ["workspace-mgr", "comms-mgr"],
  "source": "builtin | imported | custom",
  "instructions": "skills/email-drafter/instructions.md",
  "examples": "skills/email-drafter/examples.md"
}
```

### Skill Lifecycle

1. **Built-in Skills** — ship with GClaw. Email drafting, meeting scheduling, code review, research summarization, image generation, etc. Pre-configured but customizable.
2. **Imported Skills** — install from a skill registry (like npm for agent skills). Community or curated skills. Each declares tool dependencies and agent grants.
3. **Custom Skills (User-Designed)** — users create skills through conversation: "Create a skill that checks my portfolio performance every morning and sends me a summary if anything moved more than 5%." The agent generates the skill definition, instructions, and config — user reviews and activates.
4. **Dynamic Invocation** — agents discover and invoke skills based on context. The skill registry is searchable by description and context tags. When an agent encounters a situation matching a skill's trigger contexts, it can auto-invoke.

## Memory Architecture

### Three Memory Layers

**Layer 1 — Working Memory (Ephemeral)**
- Current conversation context in the Gemini context window
- Discarded when session ends
- Cost: token usage only

**Layer 2 — Session Memory (Firestore)**
- Full conversation history for the active session
- Persisted to Firestore `sessions` collection
- Survives page refreshes and reconnects
- Lifetime: until session ends or compacts

**Layer 3 — Long-Term Memory (Vertex AI Memory Bank)**
- Distilled facts, preferences, decisions
- Semantic search retrieval
- Permanent (optional TTL)
- Shared across agents via scoping
- Cost: ~$8/mo for single user

### Session Lifecycle and Compaction

1. **Session Start** — create Firestore session doc, retrieve relevant long-term memories from Memory Bank (semantic search), load soul + agent.md, inject all into Gemini system prompt.
2. **During Session** — each turn appended to Firestore. After each turn: fire-and-forget capture to Memory Bank (extracts facts from last exchange). If context window fills: mid-session compaction (summarize older turns, keep recent).
3. **Session End / Compaction** — full session history sent to `memories:generate` for extraction. Consolidation LLM deduplicates against existing memories. Session doc marked as `compacted`. Raw history retained for configurable period (audit trail).
4. **Next Session** — fresh context window, pre-loaded with relevant long-term memories. Seamless continuity without carrying forward raw history.

### Memory Scoping

- **User-scoped** `{user_id: "sbens"}` — shared across all agents. General preferences, personality, cross-domain facts. Where soul evolution persists.
- **Agent-scoped** `{user_id: "sbens", agent: "workspace-mgr"}` — domain-specific knowledge per agent per user.
- **Cross-user** `{shared_channel: "sbens_wife_shared"}` — consent-based shared channels between connected users.

### Memory Topics

**Google managed:**
- `USER_PREFERENCES` — likes, dislikes, styles, habits
- `EXPLICIT_INSTRUCTIONS` — "Always...", "Never...", "Remember that..."
- `KEY_CONVERSATION_DETAILS` — milestones, decisions, key events

**Custom:**
- `project_context` — projects, repos, teams, deadlines
- `action_items` — tasks, deadlines, commitments
- `relationships` — people, contacts, team dynamics
- `routines` — daily patterns, habits, schedules
- `domain_knowledge` — technical, professional, personal knowledge

### Soul Evolution via Memory

Soul files (`soul/base.md`, `soul/workspace.md`, etc.) are not static — they are generated from memories.

- As the Memory Bank accumulates preferences, instructions, and feedback, the system periodically regenerates soul files from relevant memory topics
- User corrections during conversation → captured as memories → soul files updated on next sync
- Soul files are cached, curated snapshots of the memory store, optimized for injection into system prompts
- Users can also directly edit soul files (they're markdown), and edits sync back to Memory Bank
- Bidirectional: memories → soul files (auto-generated) and soul files → memories (user edits synced)

## Authentication & Multi-User

### Firebase Authentication

Google Sign-In as primary method. Each user gets an isolated data silo: their own Firestore sub-collections, their own Memory Bank scopes, their own agent instances.

### Per-User Agent Instances

Each user's agent hierarchy is fully independent. Orchestrator, managers, specialists, souls, skills — all scoped to the user ID. No shared agent state between users.

### Cross-User Connection (A2A Protocol)

Consent-based connection flow:

1. **Request** — User A's agent sends a connection request via A2A protocol to User B's agent
2. **Notify** — User B gets a push notification: "User A's agent wants to connect"
3. **Accept** — User B approves, creating a shared connection record in both users' Firestore
4. **Scoped channel** — A shared Memory Bank scope is created for the connection
5. **Communicate** — Agents can exchange tasks and information through the shared scope
6. **Revoke** — Either user can disconnect at any time, purging the shared scope

### Permission Levels for Connected Agents

- **Read** — can query shared memories
- **Write** — can add to shared scope
- **Task** — can create tasks on the other user's board
- **Full** — all of the above

## Deployment Architecture

| Service | Google Product | Purpose |
|---|---|---|
| Web App | Firebase Hosting | Static Next.js PWA via CDN |
| Agent Backend | Cloud Run | Orchestration + ADK agents (scales to zero) |
| Heartbeat & Crons | Cloud Scheduler → Cloud Functions | Scheduled triggers |
| Real-time State | Firestore | Sessions, board, agent state, configs |
| Long-term Memory | Vertex AI Memory Bank | Managed memory with semantic search |
| AI Models | Gemini Pro / Flash (ADK) | Agent reasoning and tool use |
| Voice | Gemini Live API | Real-time voice conversation |
| Image Generation | Gemini Image Pro | Image creation |
| Auth | Firebase Authentication | Google Sign-In |
| Notifications | Firebase Cloud Messaging | Push notifications |
| Cross-User Comms | A2A Protocol (over Cloud Run) | Agent-to-agent between users |

## Cost Model — Single User, Active Daily Use

Based on ~50 interactions/day, 15-min heartbeat, 5 crons, moderate tool usage.

| Service | Usage Estimate | Monthly Cost |
|---|---|---|
| Gemini API (Pro + Flash) | ~50 turns/day, Pro for orchestration, Flash for specialists | $15–30 |
| Gemini Live API (Voice) | ~30 min voice/day | $5–15 |
| Vertex AI Memory Bank | ~1K memories, ~1.5K retrievals/mo | $5–10 |
| Firestore | Sessions, board, agent state, real-time listeners | $1–5 |
| Cloud Run | Scales to zero, pay per request-second | $3–10 |
| Cloud Scheduler + Functions | Heartbeat every 15 min + 5 user crons | $0–2 |
| Firebase (Hosting + Auth + FCM) | Static hosting, auth, push notifications | $0 (free tier) |
| Gemini Image Pro | ~10 images/day on active days | $2–5 |
| **Total** | | **$30–75/mo** |

### Cost Optimization Levers

- **Model routing** — Gemini Flash for simple tasks, Pro for orchestration and complex reasoning
- **Heartbeat frequency** — start at 15 min, increase to 30 min or 1 hr if proactive features aren't needed constantly
- **Memory retrieval caching** — cache frequently-used memories client-side
- **Smart heartbeat** — skip full reasoning if kanban is empty and no calendar events are imminent
- **Aggressive compaction** — shorter session retention, rely on Memory Bank for long-term recall

### Scaling Path

- **Phase 1: Solo** — single Cloud Run instance, Firestore free tier. ~$30-75/mo.
- **Phase 2: Family/friends (~5 users)** — Cloud Run auto-scales, Firestore low tier, cross-user A2A active. ~$150-300/mo total.
- **Phase 3: Broader audience** — Cloud Run + Firestore scale linearly. Consider per-user billing, premium tiers. Move to GKE only if Cloud Run limits become a bottleneck.

## Project Config Structure

Config files live in the project repository and are deployed as part of the Cloud Run container image. At runtime, they are read from the container filesystem and injected into agent system prompts. User-specific overrides (soul customizations, skill configs) are stored in Firestore and merged at runtime.

```
gclaw/
  soul/
    base.md                   # Global user personality, style, general prefs
    workspace.md              # Work habits, email tone, meeting prefs
    dev.md                    # Coding style, PR approach, tech preferences
    home.md                   # Routines, comfort prefs, device setup
    comms.md                  # Communication style per platform
    research.md               # Research depth, source prefs, summary style
  agents/
    orchestrator.md           # Root orchestrator role & routing logic
    workspace-mgr.md          # Manager role, tool grants, escalation rules
    dev-mgr.md
    home-mgr.md
    comms-mgr.md
    research-mgr.md
  tools/
    tools.md                  # Tool registry & capability map
    gmail.py
    calendar.py
    github.py
    ...
  skills/
    skills.md                 # Skill registry & discovery index
    email-drafter/
      skill.json              # Manifest (trigger, config, grants)
      instructions.md         # How to perform the skill
      examples.md             # Few-shot examples
    inbox-triage/
      skill.json / instructions.md / examples.md
    morning-briefing/
      skill.json / instructions.md / examples.md
    ...
  crons/
    crons.md                  # Cron registry
    heartbeat.json            # Heartbeat config (interval, context sources)
    weekly-report.json        # User-defined crons
    morning-briefing.json
```

## Firestore Schema

```
users/
  {userId}/
    profile                   # Auth info, settings, preferences
    sessions/
      {sessionId}             # Message history, status, metadata
    board/
      {taskId}                # Kanban task cards
    agents/
      {agentId}               # Agent state, health, last heartbeat
    crons/
      {cronId}                # Cron definitions, last run, next run
    skills/
      {skillId}               # Installed skills, config overrides
    connections/
      {connectionId}          # Cross-user consent records
```

## Onboarding Flow

When a new user signs up, the orchestrator runs an onboarding interview to build the initial soul profile:

1. Introduce itself and explain its capabilities
2. Ask about communication preferences (tone, verbosity, formality)
3. Ask about daily routines and priorities
4. Ask about professional context (role, tools used, workflows)
5. Ask about personal context (interests, family, smart home setup)
6. Generate initial soul files from the interview
7. Sync soul to Vertex AI Memory Bank
8. Offer to set up initial crons (morning briefing, inbox triage, etc.)
9. Begin normal operation

The soul evolves from this starting point through ongoing conversation and corrections.
