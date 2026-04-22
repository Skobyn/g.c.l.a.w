"""Shared-context tool functions — blackboard read/write for agents.

All tools return strings and never raise into the ADK invocation path
(match the style of ``comms_tools``).
"""

from __future__ import annotations

import base64
import json
import logging

from gclaw.shared_context.service import SharedContextService
from gclaw.tools.catalog.builtin_registry import tool_export

logger = logging.getLogger(__name__)

# Module-level holder; main.py calls set_context_service(svc) once during
# startup. The module-level shape mirrors recorder/set_recorder wiring
# used elsewhere (see gclaw.usage.recorder).
_service: SharedContextService | None = None


def set_context_service(svc: SharedContextService | None) -> None:
    global _service
    _service = svc


def _require() -> SharedContextService:
    if _service is None:
        raise RuntimeError("shared-context service not configured")
    return _service


def _err(verb: str, exc: Exception) -> str:
    logger.warning("context_%s failed: %s", verb, exc)
    return f"context_{verb} failed: {exc}"


def _parse_metadata(metadata_json: str) -> dict:
    if not metadata_json:
        return {}
    try:
        parsed = json.loads(metadata_json)
        if isinstance(parsed, dict):
            return parsed
        return {}
    except Exception:
        return {}


def _preview(text: str | None, limit: int = 120) -> str:
    if not text:
        return ""
    flat = text.replace("\n", " ").strip()
    if len(flat) <= limit:
        return flat
    return flat[: limit - 1] + "\u2026"


@tool_export(description="Write a text entry to a shared-context namespace.")
async def context_write(
    namespace: str,
    content: str,
    metadata_json: str = "",
) -> str:
    """Write a text entry to the shared-context namespace.

    Returns a short confirmation string with the entry id.
    """
    try:
        svc = _require()
        entry = svc.write_text(
            namespace=namespace,
            content=content,
            created_by="agent",
            metadata=_parse_metadata(metadata_json),
        )
    except Exception as e:
        return _err("write", e)
    where = "inline" if entry.content is not None else f"blob {entry.blob_url}"
    return f"Wrote context entry {entry.id} to namespace {namespace!r} ({where})."


@tool_export(description="Return the latest entry's content for a shared-context namespace.")
async def context_read_latest(namespace: str) -> str:
    """Return the latest entry's content for this namespace.

    Inline entries are returned directly. Blob entries return a short
    note plus a signed URL for retrieval.
    """
    try:
        svc = _require()
        entry = svc.read_latest(namespace)
    except Exception as e:
        return _err("read_latest", e)

    if entry is None:
        return f"No entries in namespace {namespace!r}."

    if entry.content is not None:
        header = f"[{entry.timestamp.isoformat()}] {entry.created_by or '?'} (id={entry.id})"
        return f"{header}\n{entry.content}"

    if entry.blob_url:
        try:
            url = svc.signed_url_for(entry, minutes=15) or entry.blob_url
        except Exception:
            url = entry.blob_url
        return (
            f"Entry {entry.id} in {namespace!r} is a blob "
            f"(mime={entry.blob_mime or '?'}). Signed URL (15m): {url}"
        )

    return f"Entry {entry.id} in {namespace!r} is empty."


@tool_export(description="List the newest entries in a shared-context namespace.")
async def context_list(namespace: str, limit: int = 10) -> str:
    """Return newline-separated rows for the namespace (newest first).

    Format: ``[ts] created_by — <preview 120 chars> (id)``.
    """
    try:
        svc = _require()
        entries = svc.list(namespace, limit=limit)
    except Exception as e:
        return _err("list", e)

    if not entries:
        return f"No entries in namespace {namespace!r}."

    rows: list[str] = []
    for e in entries:
        ts = e.timestamp.isoformat()
        who = e.created_by or "?"
        if e.content is not None:
            preview = _preview(e.content)
        elif e.blob_url:
            preview = f"<blob {e.blob_mime or '?'}>"
        else:
            preview = ""
        rows.append(f"[{ts}] {who} — {preview} ({e.id})")
    return "\n".join(rows)


@tool_export(description="Write a base64-encoded image blob to a shared-context namespace.")
async def context_write_image(
    namespace: str,
    image_base64: str,
    mime: str = "image/png",
    metadata_json: str = "",
) -> str:
    """Write a base64-encoded image blob to the namespace.

    Returns entry id + gs:// URL on success.
    """
    try:
        data = base64.b64decode(image_base64, validate=False)
    except Exception as e:
        return _err("write_image", e)

    try:
        svc = _require()
        entry = svc.write_image(
            namespace=namespace,
            data=data,
            mime=mime,
            created_by="agent",
            metadata=_parse_metadata(metadata_json),
        )
    except Exception as e:
        return _err("write_image", e)

    return f"Wrote image entry {entry.id} to {namespace!r} at {entry.blob_url}."
