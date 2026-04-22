"""Comms tool functions — Google Chat via gws CLI."""

from __future__ import annotations

import json
import logging

from gclaw.tools.catalog.builtin_registry import tool_export
from gclaw.tools.gws import GwsError, run_gws

logger = logging.getLogger(__name__)


def _err(verb: str, exc: Exception) -> str:
    logger.warning("comms tool %s failed: %s", verb, exc)
    return f"Comms {verb} failed: {exc}"


@tool_export(description="List Google Chat spaces the user is a member of.")
async def list_chat_spaces() -> str:
    """List Google Chat spaces the user is a member of."""
    try:
        result = await run_gws("chat", "spaces.list")
    except GwsError as e:
        return _err("list chat spaces", e)

    spaces = result.get("spaces") or []
    if not spaces:
        return "No chat spaces."

    lines = [
        f"- {s.get('displayName', s.get('name', '?'))} ({s.get('name', '?')})"
        for s in spaces
    ]
    return "\n".join(lines)


@tool_export(description="Post a message to a Google Chat space.")
async def post_chat_message(space_name: str, text: str) -> str:
    """Post a message to a Google Chat space."""
    try:
        result = await run_gws(
            "chat", "spaces.messages.create",
            "--params", json.dumps({"parent": space_name}),
            "--json", json.dumps({"text": text}),
        )
    except GwsError as e:
        return _err("post chat message", e)

    return f"Message sent to {space_name}: {result.get('name', '?')}"
