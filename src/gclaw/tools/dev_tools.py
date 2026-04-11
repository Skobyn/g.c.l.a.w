"""Thin agent-tool functions wrapping `gh` and local dev commands."""

from __future__ import annotations

import asyncio
import logging
import subprocess
from pathlib import Path

from gclaw.tools.gh import GhError, run_gh

logger = logging.getLogger(__name__)


def _err(verb: str, exc: Exception) -> str:
    logger.warning("dev tool %s failed: %s", verb, exc)
    return f"Dev {verb} failed: {exc}"


async def list_open_prs() -> str:
    """List open pull requests in the current repository."""
    try:
        prs = await run_gh(
            "pr", "list",
            "--state", "open",
            "--json", "number,title,author",
        )
    except GhError as e:
        return _err("list open PRs", e)

    if not prs:
        return "No open PRs."

    lines: list[str] = []
    for pr in prs:
        author = pr.get("author", {}).get("login", "?")
        lines.append(f"- #{pr.get('number', '?')} {pr.get('title', '(no title)')} — {author}")
    return "\n".join(lines)


async def get_pr_diff(pr_number: int) -> str:
    """Fetch the unified diff of a pull request."""
    try:
        text = await run_gh("pr", "diff", str(pr_number), parse_json=False)
    except GhError as e:
        return _err(f"get PR #{pr_number} diff", e)

    if len(text) > 8000:
        text = text[:8000] + "\n... (truncated)"
    return text


async def list_failing_workflows() -> str:
    """List GitHub Actions workflow runs that have failed recently."""
    try:
        runs = await run_gh(
            "run", "list",
            "--status", "failure",
            "--limit", "10",
            "--json", "name,status,conclusion,displayTitle,createdAt",
        )
    except GhError as e:
        return _err("list failing workflows", e)

    if not runs:
        return "No failing workflows."

    lines = [
        f"- {r.get('name', '?')}: {r.get('conclusion', '?')} — {r.get('displayTitle', '?')}"
        for r in runs
    ]
    return "\n".join(lines)


async def create_issue(title: str, body: str = "") -> str:
    """Create a GitHub issue in the current repository."""
    try:
        url = await run_gh(
            "issue", "create",
            "--title", title,
            "--body", body or "",
            parse_json=False,
        )
    except GhError as e:
        return _err("create issue", e)

    return url


async def get_current_diff(staged_only: bool = False) -> str:
    """Return the current working-tree diff (staged + unstaged by default)."""
    try:
        args = ["git", "diff"]
        if staged_only:
            args.append("--cached")
        result = await asyncio.to_thread(
            subprocess.run, args, capture_output=True, text=True
        )
    except Exception as e:
        return _err("get current diff", e)

    if result.returncode != 0:
        return _err("get current diff", RuntimeError(result.stderr or "non-zero exit"))

    text = result.stdout or "(no changes)"
    if len(text) > 8000:
        text = text[:8000] + "\n... (truncated)"
    return text


async def read_local_file(path: str) -> str:
    """Read a local file from disk."""
    p = Path(path)
    if not p.exists():
        return f"File not found: {path}"
    try:
        content = await asyncio.to_thread(p.read_text, encoding="utf-8")
    except Exception as e:
        return _err(f"read {path}", e)

    if len(content) > 8000:
        content = content[:8000] + "\n... (truncated)"
    return content
