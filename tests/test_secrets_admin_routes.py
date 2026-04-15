"""Tests for /admin/secrets routes."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from gclaw.api.secrets_routes import init_secrets_router
from gclaw.catalog.secret_manager import (
    SecretManagerNotFoundError,
    SecretManagerPermissionError,
)


class FakeSMService:
    def __init__(self):
        self.writes: list[dict] = []
        self.rotates: list[dict] = []
        self.list_result: list[dict] = []
        self.write_exc: Exception | None = None
        self.rotate_exc: Exception | None = None
        self.list_exc: Exception | None = None

    def write(self, *, name: str, value: str, create_if_missing: bool = True):
        if self.write_exc is not None:
            raise self.write_exc
        self.writes.append(
            {"name": name, "value": value, "create_if_missing": create_if_missing}
        )
        norm = name if name.startswith("watson-") else f"watson-{name}"
        return {
            "name": norm,
            "path": f"projects/p/secrets/{norm}/versions/latest",
            "version_id": "1",
            "created_secret": True,
        }

    def rotate(self, *, name: str, value: str):
        if self.rotate_exc is not None:
            raise self.rotate_exc
        self.rotates.append({"name": name, "value": value})
        norm = name if name.startswith("watson-") else f"watson-{name}"
        return {
            "name": norm,
            "path": f"projects/p/secrets/{norm}/versions/latest",
            "version_id": "2",
        }

    def list_gclaw_secrets(self):
        if self.list_exc is not None:
            raise self.list_exc
        return list(self.list_result)


def _make_app(svc):
    app = FastAPI()
    app.include_router(init_secrets_router(svc))
    from gclaw.auth.dependencies import get_current_user_id
    app.dependency_overrides[get_current_user_id] = lambda: "test_user"
    return app


@pytest.fixture
def svc():
    return FakeSMService()


@pytest.fixture
async def client(svc):
    app = _make_app(svc)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_write_happy_path(client, svc):
    resp = await client.post(
        "/admin/secrets",
        json={"name": "watson-openai-key", "value": "sk-abc"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "watson-openai-key"
    assert body["path"].endswith("/versions/latest")
    assert body["version_id"] == "1"
    assert body["created_secret"] is True
    assert svc.writes == [
        {
            "name": "watson-openai-key",
            "value": "sk-abc",
            "create_if_missing": True,
        }
    ]


@pytest.mark.asyncio
async def test_write_rejects_invalid_name(client):
    resp = await client.post(
        "/admin/secrets",
        json={"name": "Bad Name!", "value": "sk"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_write_rejects_empty_value(client):
    resp = await client.post(
        "/admin/secrets",
        json={"name": "watson-k", "value": ""},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_write_conflict_when_missing_and_no_create(client, svc):
    svc.write_exc = SecretManagerNotFoundError("nope")
    resp = await client.post(
        "/admin/secrets",
        json={
            "name": "watson-k",
            "value": "sk",
            "create_if_missing": False,
        },
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_write_permission_error_exposes_helpful_500(client, svc):
    svc.write_exc = SecretManagerPermissionError(
        "needs roles/secretmanager.secretVersionAdder"
    )
    resp = await client.post(
        "/admin/secrets",
        json={"name": "watson-k", "value": "sk"},
    )
    assert resp.status_code == 500
    assert "roles/secretmanager" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_list_returns_secrets(client, svc):
    svc.list_result = [
        {
            "name": "watson-openai-key",
            "path": "projects/p/secrets/watson-openai-key/versions/latest",
            "latest_version_created_at": "2026-04-14T00:00:00+00:00",
        },
    ]
    resp = await client.get("/admin/secrets")
    assert resp.status_code == 200
    body = resp.json()
    assert body["secrets"][0]["name"] == "watson-openai-key"


@pytest.mark.asyncio
async def test_rotate_happy_path(client, svc):
    resp = await client.post(
        "/admin/secrets/watson-openai-key/rotate",
        json={"value": "sk-new"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "watson-openai-key"
    assert body["version_id"] == "2"
    assert svc.rotates == [{"name": "watson-openai-key", "value": "sk-new"}]


@pytest.mark.asyncio
async def test_rotate_404_when_missing(client, svc):
    svc.rotate_exc = SecretManagerNotFoundError("missing")
    resp = await client.post(
        "/admin/secrets/watson-unknown/rotate",
        json={"value": "x"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_rotate_rejects_empty_value(client):
    resp = await client.post(
        "/admin/secrets/watson-k/rotate",
        json={"value": ""},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_503_when_service_not_configured():
    app = _make_app(None)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/admin/secrets")
    assert resp.status_code == 503
