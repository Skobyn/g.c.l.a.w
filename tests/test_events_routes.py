"""Tests for the user-scoped /api/events SSE endpoint + UserEventRegistry.

The SSE endpoint itself is hard to unit-test synchronously because
StreamingResponse keeps the connection open indefinitely until the
client disconnects — TestClient.stream() ends up waiting for either
an event or a heartbeat tick before __enter__ returns. We cover:

  1. Unauthenticated requests return 401.
  2. UserEventRegistry put/subscribe/unsubscribe mechanics (direct).

Live streaming is verified in deployment smoke tests, not here.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from gclaw.api.events_routes import build_events_router
from gclaw.observability.user_event_registry import UserEventRegistry


class _PinUserMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, user_id: str | None = "u_test"):
        super().__init__(app)
        self._user_id = user_id

    async def dispatch(self, request: Request, call_next):
        request.state.user_id = self._user_id
        return await call_next(request)


def _app_with(user_id: str | None, registry: UserEventRegistry) -> FastAPI:
    app = FastAPI()
    app.add_middleware(_PinUserMiddleware, user_id=user_id)
    app.include_router(
        build_events_router(user_event_registry=registry, heartbeat_seconds=0.05)
    )
    return app


def test_events_endpoint_requires_auth():
    reg = UserEventRegistry()
    app = _app_with(user_id=None, registry=reg)
    client = TestClient(app)
    resp = client.get("/api/events")
    assert resp.status_code == 401


# ── UserEventRegistry unit tests ────────────────────────────────────


def test_user_event_registry_put_and_subscribe():
    """Events pushed via put_nowait are drainable by a subscriber."""
    reg = UserEventRegistry()
    payload = {"event": "task.created", "data": {"task_id": "t_1"}}
    reg.put_nowait("u_1", payload)

    async def go():
        q = await reg.subscribe("u_1")
        event = await asyncio.wait_for(q.get(), timeout=1.0)
        await reg.unsubscribe("u_1")
        return event

    got = asyncio.run(go())
    assert got == payload


def test_user_event_registry_keys_scoped_per_user():
    """Events for user A don't leak to user B's queue."""
    reg = UserEventRegistry()
    reg.put_nowait("u_alice", {"event": "x", "data": {"task_id": "ta"}})
    reg.put_nowait("u_bob", {"event": "x", "data": {"task_id": "tb"}})

    async def go():
        qa = await reg.subscribe("u_alice")
        qb = await reg.subscribe("u_bob")
        ea = await asyncio.wait_for(qa.get(), timeout=1.0)
        eb = await asyncio.wait_for(qb.get(), timeout=1.0)
        return ea, eb

    ea, eb = asyncio.run(go())
    assert ea["data"]["task_id"] == "ta"
    assert eb["data"]["task_id"] == "tb"


def test_user_event_registry_put_nowait_empty_user_is_noop():
    reg = UserEventRegistry()
    reg.put_nowait("", {"event": "x"})
    assert reg.stats() == {}


def test_user_event_registry_drops_oldest_when_full():
    reg = UserEventRegistry(max_queue_size=2)
    reg.put_nowait("u_1", {"event": "a", "data": {"n": 1}})
    reg.put_nowait("u_1", {"event": "b", "data": {"n": 2}})
    reg.put_nowait("u_1", {"event": "c", "data": {"n": 3}})
    stats = reg.stats()
    assert stats["u_1"]["dropped"] >= 1


def test_user_event_registry_unsubscribe_gc_on_idle():
    """Channel is GC'd when last subscriber leaves and queue is empty."""
    reg = UserEventRegistry()

    async def go():
        q = await reg.subscribe("u_gc")
        await reg.unsubscribe("u_gc")

    asyncio.run(go())
    # After the last unsubscribe on an empty queue, the channel goes away.
    assert reg.stats() == {}
