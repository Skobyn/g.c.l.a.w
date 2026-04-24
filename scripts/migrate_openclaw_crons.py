"""Rewrite cron payloads that reference ``~/.openclaw/...`` paths.

GClaw's shared-context service (Firestore + GCS) replaces the
filesystem layout from openclaw. Cron agents should call the
``context_*`` tools against namespaces instead of reading file paths
that don't exist inside Cloud Run.

Usage::

    # Dry run — prints planned changes, writes a JSON diff file.
    python scripts/migrate_openclaw_crons.py

    # Apply — PATCHes each cron.
    python scripts/migrate_openclaw_crons.py --apply

Backend URL resolves from ``GCLAW_BACKEND_URL`` env var, defaulting
to the current production URL. Auth is a bearer token (``dev-user``
in dev-bypass deploys; override with ``GCLAW_BEARER``).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

DEFAULT_BASE = "https://gclaw-qkaevtm7wq-uc.a.run.app"
DEFAULT_BEARER = "dev-user"


# ── Rewrite rules ──────────────────────────────────────────────────

# `~/.openclaw/shared-context/<namespace-segments>/` — namespaces can
# be nested (e.g. `research/scott` → `research:scott`). Strip the
# trailing slash, convert `/` separator to `:` for Firestore doc safety.
_CTX_RE = re.compile(r"~/\.openclaw/shared-context/([\w:/.-]+?)/?(?=[\s.,)\]]|$)")
_SKILL_RE = re.compile(
    r"~/\.openclaw/workspace/skills/([\w-]+)/SKILL\.md"
)
# Anything else — fallback so unexpected paths get flagged.
_LEFTOVER_RE = re.compile(r"~/\.openclaw/[^\s]+")


def _ns(path: str) -> str:
    """Normalize a shared-context path into a Firestore-safe namespace.

    `queue/scott` → `queue:scott`
    `hot-takes`   → `hot-takes`
    """
    return path.strip("/").replace("/", ":")


def rewrite_message(message: str) -> tuple[str, list[str]]:
    """Return the rewritten message + list of warnings.

    Warnings include any ``~/.openclaw/...`` path we couldn't
    confidently map — a human should eyeball those before shipping.
    """
    warnings: list[str] = []

    def _ctx_sub(m: re.Match[str]) -> str:
        raw = m.group(1)
        return f"the `{_ns(raw)}` shared-context namespace (use context_read_latest / context_list / context_write)"

    def _skill_sub(m: re.Match[str]) -> str:
        return f"the `{m.group(1)}` skill"

    out = _CTX_RE.sub(_ctx_sub, message)
    out = _SKILL_RE.sub(_skill_sub, out)

    for leftover in _LEFTOVER_RE.findall(out):
        warnings.append(f"unmapped path: {leftover}")

    # Append a short reminder so the LLM knows to use context_* tools,
    # not file IO.
    preamble = (
        "Storage note: use the `context_*` tools to read and write "
        "shared-context namespaces (Firestore-backed). Do NOT treat "
        "any paths below as filesystem locations — they are namespace "
        "identifiers.\n\n"
    )
    if preamble.strip() not in out:
        out = preamble + out
    return out, warnings


# ── I/O ────────────────────────────────────────────────────────────


def _http(method: str, url: str, bearer: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        url,
        method=method,
        headers={
            "Authorization": f"Bearer {bearer}",
            "Content-Type": "application/json",
        },
        data=json.dumps(body).encode() if body is not None else None,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"HTTP {e.code} on {method} {url}: {e.read().decode()[:200]}")


def list_crons(base: str, bearer: str) -> list[dict]:
    return _http("GET", f"{base}/crons", bearer)  # type: ignore[return-value]


def patch_cron(base: str, bearer: str, cron_id: str, payload: dict) -> dict:
    return _http(
        "PATCH", f"{base}/crons/{cron_id}", bearer, {"payload": payload}
    )


# ── Main ───────────────────────────────────────────────────────────


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--apply",
        action="store_true",
        help="Actually PATCH the crons. Default is dry-run.",
    )
    p.add_argument(
        "--diff-file",
        default="/tmp/openclaw_cron_migration.json",
        help="Where to write the dry-run diff report.",
    )
    p.add_argument(
        "--only",
        default=None,
        help="Comma-separated cron IDs to limit the migration.",
    )
    args = p.parse_args()

    base = os.environ.get("GCLAW_BACKEND_URL", DEFAULT_BASE).rstrip("/")
    bearer = os.environ.get("GCLAW_BEARER", DEFAULT_BEARER)
    only = {s.strip() for s in args.only.split(",")} if args.only else None

    crons = list_crons(base, bearer)
    plan: list[dict] = []
    for c in crons:
        if only and c["id"] not in only:
            continue
        payload = c.get("payload") or {}
        msg = payload.get("message") or ""
        if "~/.openclaw" not in msg:
            continue
        new_msg, warnings = rewrite_message(msg)
        if new_msg == msg:
            continue
        new_payload = {**payload, "message": new_msg}
        plan.append({
            "id": c["id"],
            "title": c.get("title"),
            "assignee": c.get("assignee"),
            "warnings": warnings,
            "before": msg,
            "after": new_msg,
            "new_payload": new_payload,
        })

    print(f"Planned changes: {len(plan)} cron(s).")
    for p_ in plan:
        print(
            f"  [{p_['id']}] {p_['title']} (→ {p_['assignee']})"
            + (f"  ⚠ {len(p_['warnings'])} warnings" if p_["warnings"] else "")
        )

    with open(args.diff_file, "w") as fh:
        json.dump(plan, fh, indent=2)
    print(f"\nDry-run diff written to {args.diff_file}")

    if not args.apply:
        print("\nRun with --apply to actually patch the crons.")
        return

    print(f"\nApplying {len(plan)} patches…")
    errors = 0
    for p_ in plan:
        try:
            patch_cron(base, bearer, p_["id"], p_["new_payload"])
            print(f"  ✓ {p_['id']}")
        except SystemExit as e:
            errors += 1
            print(f"  ✗ {p_['id']}: {e}")
    print(f"\nDone. {len(plan) - errors}/{len(plan)} succeeded.")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
