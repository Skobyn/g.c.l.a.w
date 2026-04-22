"""User-scoped event feed — Server-Sent Events.

``GET /api/events``
    Streams task.* events produced anywhere in the system for the
    authenticated user. Includes events from heartbeat-driven runs
    the user isn't actively chatting in — this is how the background
    activity strip in the chat UI learns that dev-mgr's 3am heartbeat
    picked up a MEDIUM-priority task.

Authenticated via ``request.state.user_id``. Mirrors the shape of
``dashboard_routes.build_dashboard_router``.
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import StreamingResponse

from gclaw.observability.user_event_registry import UserEventRegistry

logger = logging.getLogger(__name__)

_DEFAULT_HEARTBEAT_SECONDS = 15.0


def build_events_router(
    *,
    user_event_registry: UserEventRegistry,
    heartbeat_seconds: float = _DEFAULT_HEARTBEAT_SECONDS,
) -> APIRouter:
    """Return a FastAPI router mounted at ``/api/events``."""
    router = APIRouter(prefix="/api", tags=["events"])

    @router.get("/events")
    async def stream_events(request: Request):  # noqa: D401
        user_id = getattr(request.state, "user_id", None)
        if not user_id:
            raise HTTPException(
                status_code=401, detail="authentication required"
            )

        queue = await user_event_registry.subscribe(user_id)

        async def gen():
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event = await asyncio.wait_for(
                            queue.get(), timeout=heartbeat_seconds
                        )
                    except asyncio.TimeoutError:
                        yield ": heartbeat\n\n"
                        continue
                    kind = event.get("event") or "message"
                    payload = json.dumps(event.get("data") or {})
                    yield f"event: {kind}\ndata: {payload}\n\n"
            finally:
                await user_event_registry.unsubscribe(user_id)

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    return router
