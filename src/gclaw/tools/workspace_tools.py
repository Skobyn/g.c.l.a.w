"""Thin agent-tool functions wrapping the `gws` Google Workspace CLI.

Every function is async, returns a human-readable string (not raw JSON), and
catches `GwsError` to return a graceful fallback message rather than crashing
the agent turn.
"""

from __future__ import annotations

import json
import logging

from gclaw.tools.catalog.builtin_registry import tool_export
from gclaw.tools.gws import GwsError, run_gws

logger = logging.getLogger(__name__)


def _err(verb: str, exc: Exception) -> str:
    logger.warning("workspace tool %s failed: %s", verb, exc)
    return f"Workspace {verb} failed: {exc}"


@tool_export(description="List unread email in the user's inbox.")
async def list_unread_email(max_results: int = 10) -> str:
    """List unread email in the user's inbox.

    Args:
        max_results: maximum number of unread emails to return.

    Returns:
        A formatted summary or 'No unread email.' or a failure message.
    """
    try:
        listing = await run_gws(
            "gmail", "users.messages.list",
            "--params", json.dumps({
                "userId": "me",
                "q": "is:unread in:inbox",
                "maxResults": max_results,
            }),
        )
    except GwsError as e:
        return _err("list unread email", e)

    messages = listing.get("messages") or []
    if not messages:
        return "No unread email."

    lines: list[str] = []
    for m in messages:
        try:
            detail = await run_gws(
                "gmail", "users.messages.get",
                "--params", json.dumps({
                    "userId": "me",
                    "id": m["id"],
                    "format": "metadata",
                    "metadataHeaders": ["From", "Subject"],
                }),
            )
        except GwsError as e:
            lines.append(f"- (could not fetch {m.get('id', '?')}): {e}")
            continue

        headers = {
            h["name"]: h["value"]
            for h in detail.get("payload", {}).get("headers", [])
        }
        frm = headers.get("From", "?")
        subj = headers.get("Subject", "(no subject)")
        lines.append(f"- {frm}: {subj}")

    return "\n".join(lines)


@tool_export(description="Send an email from the user's Gmail account.")
async def send_email(to: str, subject: str, body: str) -> str:
    """Send an email from the user's Gmail account.

    Args:
        to: recipient email address.
        subject: email subject line.
        body: plain-text body.

    Returns:
        Confirmation or failure message.
    """
    import base64

    rfc = f"To: {to}\r\nSubject: {subject}\r\n\r\n{body}"
    raw = base64.urlsafe_b64encode(rfc.encode("utf-8")).decode("ascii")

    try:
        result = await run_gws(
            "gmail", "users.messages.send",
            "--params", json.dumps({"userId": "me"}),
            "--json", json.dumps({"raw": raw, "to": to}),
        )
    except GwsError as e:
        return _err("send email", e)

    return f"Email sent (id: {result.get('id', '?')})"


@tool_export(description="List today's calendar events on the user's primary calendar.")
async def list_calendar_events_today() -> str:
    """List today's calendar events.

    Returns:
        Formatted summary or 'No events today.'
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    end = now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()

    try:
        result = await run_gws(
            "calendar", "events.list",
            "--params", json.dumps({
                "calendarId": "primary",
                "timeMin": start,
                "timeMax": end,
                "singleEvents": True,
                "orderBy": "startTime",
            }),
        )
    except GwsError as e:
        return _err("list calendar events", e)

    items = result.get("items") or []
    if not items:
        return "No events today."

    lines: list[str] = []
    for ev in items:
        summary = ev.get("summary", "(no title)")
        start_dt = (
            ev.get("start", {}).get("dateTime")
            or ev.get("start", {}).get("date")
            or "?"
        )
        lines.append(f"- {start_dt}: {summary}")

    return "\n".join(lines)


@tool_export(description="Create a calendar event on the user's primary calendar.")
async def create_calendar_event(
    summary: str,
    start_iso: str,
    end_iso: str,
    description: str = "",
) -> str:
    """Create a calendar event on the user's primary calendar."""
    try:
        result = await run_gws(
            "calendar", "events.insert",
            "--params", json.dumps({"calendarId": "primary"}),
            "--json", json.dumps({
                "summary": summary,
                "description": description,
                "start": {"dateTime": start_iso},
                "end": {"dateTime": end_iso},
            }),
        )
    except GwsError as e:
        return _err("create calendar event", e)

    return f"Event created: {result.get('id', '?')} — {summary}"


@tool_export(description="List the user's most recently modified Google Drive files.")
async def list_drive_files(max_results: int = 10) -> str:
    """List the user's most recently modified Drive files."""
    try:
        result = await run_gws(
            "drive", "files.list",
            "--params", json.dumps({
                "pageSize": max_results,
                "orderBy": "modifiedTime desc",
                "fields": "files(id,name,mimeType,modifiedTime)",
            }),
        )
    except GwsError as e:
        return _err("list drive files", e)

    files = result.get("files") or []
    if not files:
        return "No files."

    lines = [
        f"- {f.get('name', '?')} ({f.get('mimeType', '?')})"
        for f in files
    ]
    return "\n".join(lines)


@tool_export(description="Read the plain-text content of a Google Doc by file ID.")
async def read_drive_doc(file_id: str) -> str:
    """Read the plain-text content of a Google Doc."""
    try:
        result = await run_gws(
            "drive", "files.export",
            "--params", json.dumps({
                "fileId": file_id,
                "mimeType": "text/plain",
            }),
        )
    except GwsError as e:
        return _err("read drive doc", e)

    content = result.get("body") or result.get("content") or json.dumps(result)
    if len(content) > 4000:
        content = content[:4000] + "\n... (truncated)"
    return content
