# Contributing to GClaw

Thanks for your interest. GClaw is a small project — these guidelines
are short on purpose.

## Before you start

- Read `README.md` for the high-level shape of the system.
- Read `CLAUDE.md` for the architecture in detail (it's written for
  AI assistants but doubles as a maintainer handbook).
- Skim open issues and PRs before opening a duplicate.

## Dev setup

```bash
# Backend
uv sync --extra dev
uv run pytest                      # full suite
uv run python -m gclaw.main        # local server on :8080

# Web
cd web
npm install
npm run dev                        # next dev on :3000
npm test                           # vitest run
```

The backend reads its config from `.env` (start from `.env.example`).
The web client reads `web/.env.local` (start from
`web/.env.local.example`). Setting `FIREBASE_AUTH_ENABLED=false` and
`NEXT_PUBLIC_DEV_BYPASS_AUTH=true` lets you run end-to-end without
provisioning Firebase.

## Pull request flow

1. Branch off `master` with a descriptive name
   (`feat/<short-summary>`, `fix/<short-summary>`,
   `chore/<short-summary>`).
2. Keep PRs focused. One reviewable change per PR is much easier
   than five.
3. Match the existing commit-message style:
   `<type>(<scope>): <summary>` where `<type>` is one of `feat`,
   `fix`, `chore`, `ci`, `docs`, `refactor`, `test`. Examples in
   `git log --oneline`.
4. Run `uv run pytest` (and `npm test` if you touched `web/`) before
   opening the PR. CI gates on these.
5. Auto-merge is enabled — once Test (Python) and Claude Code Review
   pass and at least one human approval lands, the PR squashes to
   `master` and triggers a deploy.

## What lands easily

- Bug fixes with a regression test.
- Small refactors that demonstrably improve clarity.
- New tools/skills that follow the existing patterns in
  `src/gclaw/tools/` and `skills/`.
- Documentation that matches what the code actually does.

## What needs more discussion

- New manager agents (the seven existing managers cover most domains
  — open an issue first to confirm the new one isn't redundant).
- Architectural changes that cross layer boundaries (see CLAUDE.md
  "Five Layers").
- Anything that adds a hard dependency on a specific external
  service. Bias toward configurable transports and feature flags.

## Reporting bugs

Open an issue with: what you ran, what you expected, what you got
(error message + relevant traceback), and the commit SHA you're on.
For security issues, see `SECURITY.md` instead — please don't open a
public bug.
