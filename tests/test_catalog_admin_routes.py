"""Tests for the catalog admin routes."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from gclaw.api.catalog_routes import init_catalog_router
from gclaw.catalog.service import CatalogService
from gclaw.models.catalog import (
    ApiKeyKind,
    ApiKeySpec,
    ProviderKind,
)
from _catalog_fakes import FakeModelRepo, FakeProviderRepo


@pytest.fixture
def service():
    return CatalogService(
        provider_repo=FakeProviderRepo(),
        model_repo=FakeModelRepo(),
    )


@pytest.fixture
def app(service):
    app = FastAPI()
    app.include_router(init_catalog_router(service))
    from gclaw.auth.dependencies import get_current_user_id
    app.dependency_overrides[get_current_user_id] = lambda: "test_user"
    return app


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_create_list_provider(client):
    resp = await client.post(
        "/admin/model-providers",
        json={"name": "My OpenAI", "kind": "openai"},
    )
    assert resp.status_code == 200
    pid = resp.json()["id"]

    resp = await client.get("/admin/model-providers")
    assert resp.status_code == 200
    arr = resp.json()
    assert len(arr) == 1
    assert arr[0]["id"] == pid
    assert arr[0]["model_count"] == 0


@pytest.mark.asyncio
async def test_literal_api_key_redacted(client):
    resp = await client.post(
        "/admin/model-providers",
        json={
            "name": "With Key",
            "kind": "openai",
            "api_key": {"kind": "literal", "value": "sk-secret-123"},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["api_key"]["value"] == "***"

    pid = body["id"]
    resp = await client.get(f"/admin/model-providers/{pid}")
    assert resp.json()["api_key"]["value"] == "***"


@pytest.mark.asyncio
async def test_env_api_key_not_redacted(client):
    resp = await client.post(
        "/admin/model-providers",
        json={
            "name": "Env",
            "kind": "anthropic",
            "api_key": {"kind": "env", "value": "ANTHROPIC_API_KEY"},
        },
    )
    body = resp.json()
    # env reference is a pointer, not a secret
    assert body["api_key"]["value"] == "ANTHROPIC_API_KEY"


@pytest.mark.asyncio
async def test_update_and_delete_provider(client):
    resp = await client.post(
        "/admin/model-providers",
        json={"name": "A", "kind": "openai"},
    )
    pid = resp.json()["id"]

    resp = await client.patch(
        f"/admin/model-providers/{pid}",
        json={"name": "B", "enabled": False},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "B"
    assert resp.json()["enabled"] is False

    resp = await client.delete(f"/admin/model-providers/{pid}")
    assert resp.status_code == 200

    resp = await client.get(f"/admin/model-providers/{pid}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_list_models(client):
    p_resp = await client.post(
        "/admin/model-providers",
        json={"name": "P", "kind": "openai"},
    )
    pid = p_resp.json()["id"]

    resp = await client.post(
        "/admin/models",
        json={
            "provider_id": pid,
            "model_id": "gpt-4o",
            "display_name": "GPT-4o",
            "context_window": 128000,
            "capabilities": {"vision": True, "tools": True},
        },
    )
    assert resp.status_code == 200
    mid = resp.json()["id"]

    resp = await client.get(f"/admin/models?provider_id={pid}")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    resp = await client.get(f"/admin/models/{mid}")
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "GPT-4o"


@pytest.mark.asyncio
async def test_create_model_invalid_provider(client):
    resp = await client.post(
        "/admin/models",
        json={
            "provider_id": "prov_nope",
            "model_id": "x",
            "display_name": "X",
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_presets_endpoint(client):
    resp = await client.get("/admin/model-presets")
    assert resp.status_code == 200
    data = resp.json()
    assert "openai" in data
    assert "anthropic" in data
    assert any(m["model_id"] == "gpt-4o" for m in data["openai"]["models"])


@pytest.mark.asyncio
async def test_install_presets(client):
    p_resp = await client.post(
        "/admin/model-providers",
        json={"name": "OAI", "kind": "openai"},
    )
    pid = p_resp.json()["id"]

    resp = await client.post(
        f"/admin/model-providers/{pid}/install-presets",
        json={"model_ids": ["gpt-4o", "gpt-4o-mini", "nope"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["created"]) == 2
    assert body["skipped"] == ["nope"]

    resp = await client.get(f"/admin/models?provider_id={pid}")
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_provider_model_count(client):
    p_resp = await client.post(
        "/admin/model-providers",
        json={"name": "OAI", "kind": "openai"},
    )
    pid = p_resp.json()["id"]
    await client.post(
        "/admin/models",
        json={"provider_id": pid, "model_id": "a", "display_name": "A"},
    )
    resp = await client.get("/admin/model-providers")
    assert resp.json()[0]["model_count"] == 1


@pytest.mark.asyncio
async def test_delete_provider_cascades(client):
    p_resp = await client.post(
        "/admin/model-providers",
        json={"name": "OAI", "kind": "openai"},
    )
    pid = p_resp.json()["id"]
    m_resp = await client.post(
        "/admin/models",
        json={"provider_id": pid, "model_id": "a", "display_name": "A"},
    )
    mid = m_resp.json()["id"]
    await client.delete(f"/admin/model-providers/{pid}")

    resp = await client.get(f"/admin/models/{mid}")
    assert resp.status_code == 404
