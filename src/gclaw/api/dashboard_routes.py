"""Live dashboard feed — Server-Sent Events.

``GET /api/runs/{run_id}/events``
    Streams AGENT-span lifecycle events for the given run. Authenticated
    via the existing auth middleware (``request.state.user_id``); a 403
    is returned when the requesting user doesn't own the run.

Same-replica scope: the SSE subscriber only receives events produced by
the Cloud Run instance it's connected to. For strictly global status,
the PWA should also subscribe to the Firestore
``/users/{uid}/agent_runs/{run_id}`` doc via ``onSnapshot``.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import StreamingResponse

from gclaw.observability.run_registry import RunRegistry

logger = logging.getLogger(__name__)

_DEFAULT_HEARTBEAT_SECONDS = 15.0


def build_dashboard_router(
    *,
    run_registry: RunRegistry,
    owner_lookup: Callable[[str, str], bool] | None = None,
    heartbeat_seconds: float = _DEFAULT_HEARTBEAT_SECONDS,
) -> APIRouter:
    """Return a FastAPI router mounted at ``/api/runs/{run_id}/events``.

    ``owner_lookup(user_id, run_id) -> bool`` — called once per request
    to authorize the subscriber. Pass ``None`` to skip authorization
    (dev-only; production should always set it).

    ``heartbeat_seconds`` controls the interval between SSE heartbeat
    comments (keeps Cloud Run's HTTP/2 proxy from closing the stream
    as idle). Tests override to a small value to avoid 15s hangs.
    """
    router = APIRouter(prefix="/api/runs", tags=["dashboard"])

    @router.get("/{run_id}/events")
    async def stream_events(run_id: str, request: Request):  # noqa: D401
        user_id = getattr(request.state, "user_id", None)
        if not user_id:
            raise HTTPException(
                status_code=401, detail="authentication required"
            )

        if owner_lookup is not None:
            try:
                is_owner = bool(owner_lookup(user_id, run_id))
            except Exception:
                logger.warning("owner_lookup failed", exc_info=True)
                is_owner = False
            if not is_owner:
                raise HTTPException(status_code=403, detail="forbidden")

        queue = await run_registry.subscribe(run_id)

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
                await run_registry.unsubscribe(run_id)

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
