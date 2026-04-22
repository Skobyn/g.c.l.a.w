# Security Policy

## Reporting a vulnerability

If you find a security issue in GClaw, **please do not open a public
issue or PR**. Instead, email the maintainer directly:

> skobyn+security@gmail.com

Include:

- A description of the issue and the impact you believe it has.
- The smallest reproduction you can produce — commit SHA, command,
  request body, screenshot, etc.
- Whether the issue is already publicly known.

You should expect an acknowledgement within **3 business days** and a
substantive response (fix in progress, more info needed, won't-fix
with rationale) within **10 business days**. Severity is judged on a
case-by-case basis using the categories below.

## What's in scope

GClaw is an agent orchestration framework that runs in your own GCP
project. The maintainers consider the following in scope for security
reports:

- **Auth bypass** — any way to obtain another user's session, token,
  or scoped data via the FastAPI surface or the web client.
- **Tool execution escalation** — a request that causes an agent to
  execute a tool the user did not authorize (e.g. tricking
  `dev-mgr` into running `gh` against an unrelated repo, or
  injecting prompt content that makes a manager invoke a tool with
  attacker-controlled arguments).
- **Secret exposure** — any code path that leaks Secret Manager
  values, OAuth tokens, or credential files in logs, traces, error
  bodies, or HTTP responses.
- **Code execution** — anything that lets attacker input run inside
  the backend container or the code-exec sandbox outside its
  designed isolation.
- **Memory/board cross-tenant leak** — when Firebase Auth is on and
  multi-user mode is in use, any path where one user's
  Firestore-backed session/board/memory is readable or writable by
  another.
- **Supply chain** — credentials or build artefacts ending up in a
  published Docker image or in the Cloud Build cache.

## What's out of scope

- Vulnerabilities that require admin access to the user's own GCP
  project (you already had everything).
- Bugs that depend on the user disabling Firebase Auth in
  production. The dev-bypass middleware is intentionally permissive.
- Denial of service from running expensive Gemini calls — Vertex AI
  quotas are the user's responsibility.
- Issues in third-party services (Vertex AI, Firestore, Postiz,
  Anthropic, OpenRouter) — report those upstream.

## Coordinated disclosure

If you'd like to publish a writeup, please coordinate the timing
with the maintainers. We aim to ship a fix and a patched release
before any public disclosure.
