"""Tools for the agent-architect agent.

The architect creates new agents in-process by either:

  1. Writing markdown files into ``GCLAW_CONFIG_DIR/agents/`` and
     ``GCLAW_CONFIG_DIR/soul/`` (file-backed, requires a redeploy or
     a restart for the factory to pick them up at next boot), or

  2. Calling :func:`AgentConfigService.create_standalone` to register
     a Firestore-only standalone agent that joins the running graph
     immediately on next ``factory.build`` call.

Standalone-on-Firestore is the recommended path for runtime creation —
no redeploy, the override IS the source of truth, and the admin UI can
edit it through ``PATCH /admin/agents/{name}``.

All file-write tools refuse to escape ``GCLAW_CONFIG_DIR`` (path
traversal guard) and refuse to overwrite existing files unless
``allow_overwrite=True`` is passed explicitly. Same restriction applies
to deleting standalone agents that would clobber a baseline file.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from gclaw.config.agent_config_service import AgentConfigService

logger = logging.getLogger(__name__)


_AGENT_NAME_OK = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
)


# Module-level service handle, set at startup by main.py via
# :func:`set_agent_config_service`. The tools refuse to operate when
# the service is unset — this happens in tests and in deployments
# where Firestore is unavailable.
_agent_config_service: AgentConfigService | None = None


def set_agent_config_service(svc: AgentConfigService | None) -> None:
    global _agent_config_service
    _agent_config_service = svc


def _require_service() -> AgentConfigService:
    if _agent_config_service is None:
        raise RuntimeError(
            "agent_config_service not configured — architect tools "
            "cannot mutate Firestore. Wire it via "
            "set_agent_config_service(svc) at app boot."
        )
    return _agent_config_service


def _config_dir() -> str:
    return os.environ.get("GCLAW_CONFIG_DIR", os.getcwd())


def _validate_name(name: str) -> None:
    if not name:
        raise ValueError("agent name is required")
    if any(c not in _AGENT_NAME_OK for c in name):
        raise ValueError(
            f"agent name {name!r} contains invalid chars; allowed: "
            "alphanumeric, '-', '_'"
        )
    if name.startswith("-") or name.startswith("_") or name.startswith("."):
        raise ValueError(
            f"agent name {name!r} cannot start with -, _, or ."
        )


def _resolve_path_within(base_subdir: str, name: str) -> str:
    """Return the absolute path for ``<config_dir>/<base_subdir>/<name>.md``.

    Refuses any name that would resolve outside the base directory
    (path-traversal guard). Used by the read/write tools below.
    """
    _validate_name(name)
    base = os.path.realpath(os.path.join(_config_dir(), base_subdir))
    target = os.path.realpath(os.path.join(base, f"{name}.md"))
    if not target.startswith(base + os.sep) and target != base:
        raise ValueError(
            f"resolved path {target!r} escapes {base!r}"
        )
    return target


# ---------- File-backed agent / soul read+write ----------


def read_agent_file(name: str) -> str:
    """Return the body of ``agents/<name>.md`` from the config dir.

    Returns a "not found" string rather than raising so the agent can
    decide how to react. Use ``list_agent_files()`` to enumerate.
    """
    try:
        path = _resolve_path_within("agents", name)
    except ValueError as e:
        return f"ERROR: {e}"
    if not os.path.isfile(path):
        return f"NOT FOUND: agents/{name}.md does not exist"
    with open(path, encoding="utf-8") as f:
        return f.read()


def read_soul_file(name: str) -> str:
    """Return the body of ``soul/<name>.md`` from the config dir."""
    try:
        path = _resolve_path_within("soul", name)
    except ValueError as e:
        return f"ERROR: {e}"
    if not os.path.isfile(path):
        return f"NOT FOUND: soul/{name}.md does not exist"
    with open(path, encoding="utf-8") as f:
        return f.read()


def list_agent_files() -> str:
    """List every agent-definition file under ``GCLAW_CONFIG_DIR/agents``."""
    base = os.path.join(_config_dir(), "agents")
    if not os.path.isdir(base):
        return f"NOT FOUND: {base} does not exist"
    names = sorted(
        f.removesuffix(".md") for f in os.listdir(base) if f.endswith(".md")
    )
    return "\n".join(names) if names else "(no agents)"


def write_agent_file(
    name: str,
    body: str,
    allow_overwrite: bool = False,
) -> str:
    """Write a new ``agents/<name>.md`` file.

    Refuses to overwrite an existing file unless ``allow_overwrite=True``.
    The file is the agent's *baseline body*; the factory picks it up at
    next ``factory.build(name)`` call (no restart needed within a single
    process; new processes pick it up on next boot).

    Returns a one-line summary of what changed.
    """
    if not body or not body.strip():
        return "ERROR: body cannot be empty"
    try:
        path = _resolve_path_within("agents", name)
    except ValueError as e:
        return f"ERROR: {e}"
    existed = os.path.isfile(path)
    if existed and not allow_overwrite:
        return (
            f"ERROR: agents/{name}.md already exists — pass "
            "allow_overwrite=True to replace"
        )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body if body.endswith("\n") else body + "\n")
    verb = "overwrote" if existed else "created"
    return f"OK: {verb} agents/{name}.md ({len(body)} chars)"


def write_soul_file(
    name: str,
    body: str,
    allow_overwrite: bool = False,
) -> str:
    """Write a new ``soul/<name>.md`` file. Same rules as ``write_agent_file``."""
    if not body or not body.strip():
        return "ERROR: body cannot be empty"
    try:
        path = _resolve_path_within("soul", name)
    except ValueError as e:
        return f"ERROR: {e}"
    existed = os.path.isfile(path)
    if existed and not allow_overwrite:
        return (
            f"ERROR: soul/{name}.md already exists — pass "
            "allow_overwrite=True to replace"
        )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body if body.endswith("\n") else body + "\n")
    verb = "overwrote" if existed else "created"
    return f"OK: {verb} soul/{name}.md ({len(body)} chars)"


# ---------- Standalone (Firestore-only) agent registration ----------


def register_standalone_agent(
    agent_name: str,
    body: str,
    display_name: str = "",
    description: str = "",
    soul_overlay: str = "",
    model_primary: str = "",
) -> str:
    """Register a new standalone agent in Firestore (no .md file).

    Standalone agents have no baseline file and the override IS the
    source of truth. They join the running graph on next
    ``factory.build`` call — no redeploy needed. Refuses if an agent
    with the same name already exists in either the file system
    (would shadow the baseline) or Firestore (would collide with an
    existing override).

    Args:
        agent_name: kebab-case identifier; used for routing.
        body: full system-prompt body text. Required.
        display_name: human-readable name for the admin UI.
        description: one-line summary of what the agent does.
        soul_overlay: agent-specific personality on top of soul/base.md.
        model_primary: catalog model ref. Examples:
          ``"gemini-2.5-flash"`` (bare id, ambiguous if multiple
          providers list it),
          ``"Anthropic/claude-haiku-4-5"`` (provider/model, explicit).

    Returns: confirmation with the new agent_name.
    """
    _validate_name(agent_name)
    svc = _require_service()
    try:
        override = svc.create_standalone(
            agent_name=agent_name,
            body=body,
            display_name=display_name or None,
            description=description or None,
            soul_overlay=soul_overlay or None,
            model_primary=model_primary or None,
        )
    except ValueError as e:
        return f"ERROR: {e}"
    return (
        f"OK: standalone agent {override.agent_name!r} registered "
        f"(model={(override.model.primary or '<router-default>')})"
    )


def update_agent_model(agent_name: str, primary: str) -> str:
    """Patch an existing agent's primary model.

    Works for both standalone and file-backed agents. The factory
    re-resolves on the next ``build`` call so the change is live
    without a restart for in-process callers — but already-built
    LlmAgent instances in memory keep the old model until the
    process recycles. Bounce the service to force a clean rebuild.
    """
    _validate_name(agent_name)
    if not primary:
        return "ERROR: primary model id is required"
    svc = _require_service()
    try:
        override = svc.upsert_override(
            agent_name, {"model": {"primary": primary}}
        )
    except ValueError as e:
        return f"ERROR: {e}"
    return (
        f"OK: {agent_name} model.primary set to {override.model.primary!r}"
    )


def list_registered_agents() -> str:
    """List every agent the platform knows about, one per line.

    Includes both baseline (file-backed) and standalone (Firestore-only)
    agents. Each line: ``<name> [baseline|standalone|override-on-baseline]
    model=<ref>``.
    """
    svc = _require_service()
    rows: list[str] = []
    for entry in svc.list_agents():
        if entry.get("is_standalone"):
            kind = "standalone"
        elif entry.get("has_override"):
            kind = "override-on-baseline"
        else:
            kind = "baseline"
        model = entry.get("model_ref") or "<router-default>"
        rows.append(f"{entry['name']} [{kind}] model={model}")
    return "\n".join(rows) if rows else "(no agents)"
