"""Tests for GET /admin/transports."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from gclaw.api.admin_routes import init_admin_router
from gclaw.cron.delivery import (
    CronDeliveryService,
    LoggingAnnounceTransport,
)


def _mk_chat_transport():
    t = MagicMock()
    t.send = AsyncMock(return_value=True)
    return t


@pytest.fixture
def transports_app():
    delivery = CronDeliveryService(
        transports={
            "logging": LoggingAnnounceTransport(),
            "google_chat": _mk_chat_transport(),
        },
        default_transport="google_chat",
    )

    app = FastAPI()
    app.include_router(
        init_admin_router(
            config_loader=MagicMock(),
            cron_delivery_service=delivery,
        )
    )
    from gclaw.auth.dependencies import get_current_user_id
    app.dependency_overrides[get_current_user_id] = lambda: "test_user"
    return app


@pytest.mark.asyncio
async def test_list_transports_returns_names_and_default(transports_app):
    transport = ASGITransport(app=transports_app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.get("/admin/transports")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["transports"]) == {"logging", "google_chat"}
    assert body["transports"] == sorted(body["transports"])
    assert body["default"] == "google_chat"


@pytest.mark.asyncio
async def test_list_transports_503_when_service_missing():
    app = FastAPI()
    app.include_router(
        init_admin_router(config_loader=MagicMock())
    )
    from gclaw.auth.dependencies import get_current_user_id
    app.dependency_overrides[get_current_user_id] = lambda: "test_user"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.get("/admin/transports")
    assert resp.status_code == 503
