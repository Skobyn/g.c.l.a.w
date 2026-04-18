"""SSE dashboard feed — auth + wire-format unit tests.

Authorization paths (401 / 403) use TestClient for deterministic
behaviour. The actual SSE streaming behaviour is exercised
end-to-end in the browser during Phase 6; unit-testing an
indefinite-stream generator across an ASGI boundary is fragile
(the server-side generator keeps yielding heartbeats until the
consumer fully unwinds the stream context, which httpx' test
transport doesn't always signal cleanly). The RunRegistry +
LiveSpanProcessor unit tests already prove events flow into the
per-run queue.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from gclaw.api.dashboard_routes import build_dashboard_router
from gclaw.observability.run_registry import RunRegistry


class _StaticUserMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, user_id: str | None) -> None:
        super().__init__(app)
        self._user_id = user_id

    async def dispatch(self, request, call_next):
        if self._user_id is not None:
            request.state.user_id = self._user_id
        return await call_next(request)


def _build_app(
    *,
    reg: RunRegistry,
    user_id: str | None = "u1",
    owners: dict[tuple[str, str], bool] | None = None,
) -> FastAPI:
    app = FastAPI()

    def owner_lookup(uid, rid):
        if owners is None:
            return True
        return bool(owners.get((uid, rid), False))

    app.include_router(
        build_dashboard_router(
            run_registry=reg,
            owner_lookup=owner_lookup,
            heartbeat_seconds=0.05,
        )
    )
    app.add_middleware(_StaticUserMiddleware, user_id=user_id)
    return app


def test_non_owner_gets_403():
    reg = RunRegistry()
    app = _build_app(reg=reg, owners={("u1", "r1"): False})

    with TestClient(app) as client:
        resp = client.get("/api/runs/r1/events")
    assert resp.status_code == 403


def test_missing_user_id_returns_401():
    reg = RunRegistry()
    app = FastAPI()
    # No middleware — request.state.user_id will be unset.
    app.include_router(
        build_dashboard_router(run_registry=reg, owner_lookup=None)
    )

    with TestClient(app) as client:
        resp = client.get("/api/runs/r1/events")
    assert resp.status_code == 401


def test_owner_lookup_exception_is_treated_as_denied():
    """A raising owner_lookup must produce 403, not 500."""
    reg = RunRegistry()
    app = FastAPI()

    def raising_lookup(uid, rid):
        raise RuntimeError("lookup backend down")

    app.include_router(
        build_dashboard_router(
            run_registry=reg, owner_lookup=raising_lookup
        )
    )
    app.add_middleware(_StaticUserMiddleware, user_id="u1")

    with TestClient(app) as client:
        resp = client.get("/api/runs/r1/events")
    assert resp.status_code == 403
