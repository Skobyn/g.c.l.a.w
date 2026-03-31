# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GClaw is a **multi-agent AI orchestration platform** built on the Google stack. It uses the Google Agent Development Kit (ADK) for agent execution and Gemini models for intelligence, with a custom orchestration layer on top (Approach B — hybrid architecture).

The platform is in active development — architecture design is complete, implementation is in progress.

## Architecture (Five Layers)

1. **User Layer** — PWA web app, Gemini Live voice, mobile. Firebase Auth for identity.
2. **Orchestration Layer** (custom-built) — Agent hierarchy, kanban project board, cron scheduler, session router. This is the differentiating layer.
3. **Agent Layer** (ADK) — Specialist and manager agents with Gemini, tool bindings, and instructions. Agents communicate through the project board, not directly.
4. **Memory Layer** — Firestore (sessions, board, config), Vertex AI Memory Bank (long-term recall), soul.md profiles.
5. **Integration Layer** — Extensible tool modules (Google Workspace, GitHub, Smart Home, etc.).

## Agent Model

Every agent has two halves:
- **agent.md** — Role, capabilities, tool grants, authority level, escalation rules
- **soul.md** — User-specific personality, preferences, communication style (evolves over time)

System prompt = `agent.md` + `soul.md` + injected memories from Vertex AI Memory Bank.

### Agent Hierarchy

- **Root Orchestrator (Soul)** — Single entry point. Intent classification, session continuity, personality, escalation handling.
- **Managers** (fixed tier) — Domain owners (Workspace, Dev, Home, Comms, Research). Can spawn specialists. Read/write project board.
- **Specialists** (dynamic tier) — Short-lived ADK agents spawned by managers for single tasks. Bound to specific tools.

## Planned Directory Structure

```
gclaw/
  soul/
    base.md              # Global user personality & style
    workspace.md         # Work habits, email tone, meeting prefs
    dev.md               # Coding style, PR approach, tech preferences
    home.md              # Routines, comfort prefs, device setup
    comms.md             # Communication style per platform
    research.md          # Research depth, source prefs, summary style
  agents/
    orchestrator.md      # Root orchestrator role & routing logic
    workspace-mgr.md     # Manager roles, tool grants, escalation rules
    dev-mgr.md
    home-mgr.md
    comms-mgr.md
    research-mgr.md
  tools/
    tools.md             # Tool registry & capability map
    gmail.py             # Tool implementation modules
    calendar.py
    github.py
    ...
```

## GCP Projects

- `apexfoundation` — compute, Cloud Run, deployer SA, Artifact Registry
- `saltwater-sync` — Firestore, GCS buckets, Firebase

## Key Design Decisions

- **Hybrid architecture (Approach B)**: ADK agents handle tool use, Gemini integration, and context management. Custom orchestration layer owns the hierarchy, kanban board, cron system, and inter-agent communication.
- **Board-based communication**: Agents don't talk to each other directly — they communicate through the kanban project board in Firestore.
- **Soul inheritance**: Base soul flows down the hierarchy. Each agent gets a domain-specific overlay. Dynamic agents inherit from their parent manager.
- **A2A protocol**: Used for cross-user agent communication. Internal communication uses custom protocol through the board.

## Skills

Skills are packaged capabilities that agents can execute — like playbooks. They live in `skills/<skill-name>/` with a `SKILL.md` entry point and supporting files.

### gcp-audit (`skills/gcp-audit/`)
- `SKILL.md` — Skill definition, execution flow, quick-audit mode
- `spec.md` — Full 11-phase audit checklist with all gcloud commands and flag criteria

Runs a comprehensive GCP infrastructure audit against CIS benchmarks, security best practices, cost optimization, and operational excellence. Intended to be executed by the Dev Manager or a spawned specialist agent.
