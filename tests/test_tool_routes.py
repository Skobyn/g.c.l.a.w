"""Tests for the /admin/tools CRUD + test-tool endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from gclaw.api.tool_routes import init_tool_router
from gclaw.tools.catalog.service import ToolCatalogService
from tests._tool_catalog_fakes import FakeToolRepo


@pytest.fixture
def service() -> ToolCatalogService:
    return ToolCatalogService(tool_repo=FakeToolRepo())


@pytest.fixture
def app(service):
    app = FastAPI()
    app.include_router(init_tool_router(service))
    from gclaw.auth.dependencies import get_current_user_id
    app.dependency_overrides[get_current_user_id] = lambda: "test_user"
    return app


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# --- Create / list -------------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_list_builtin(client):
    resp = await client.post(
        "/admin/tools",
        json={
            "name": "web_search",
            "config": {
                "kind": "builtin",
                "function_path": "gclaw.tools.research_tools.web_search",
            },
        },
    )
    assert resp.status_code == 200, resp.text
    created = resp.json()
    assert created["id"].startswith("tool_")
    assert created["kind"] == "builtin"
    assert created["config"]["kind"] == "builtin"

    resp = await client.get("/admin/tools")
    assert resp.status_code == 200
    arr = resp.json()
    assert len(arr) == 1
    assert arr[0]["id"] == created["id"]


@pytest.mark.asyncio
async def test_create_mcp_with_credential(client):
    resp = await client.post(
        "/admin/tools",
        json={
            "name": "fs",
            "config": {
                "kind": "mcp",
                "transport": "stdio",
                "endpoint": "npx fs-mcp",
            },
            "credential_ref": "projects/p/secrets/s/versions/latest",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["kind"] == "mcp"
    assert body["credential_ref"] == "projects/p/secrets/s/versions/latest"


@pytest.mark.asyncio
async def test_create_rejects_bad_config(client):
    """Discriminator mismatch → 400, not a 500."""
    resp = await client.post(
        "/admin/tools",
        json={"name": "bad", "config": {"kind": "pretend"}},
    )
    assert resp.status_code == 400
    assert "config" in resp.text.lower() or "kind" in resp.text.lower()


# --- Get / update / delete ----------------------------------------------


@pytest.mark.asyncio
async def test_get_missing_returns_404(client):
    resp = await client.get("/admin/tools/nope")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_toggles_enabled(client):
    resp = await client.post(
        "/admin/tools",
        json={
            "name": "t",
            "config": {"kind": "builtin", "function_path": "x.y.z"},
        },
    )
    tid = resp.json()["id"]

    resp = await client.patch(f"/admin/tools/{tid}", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False

    resp = await client.get(f"/admin/tools/{tid}")
    assert resp.json()["enabled"] is False


@pytest.mark.asyncio
async def test_patch_missing_returns_404(client):
    resp = await client.patch("/admin/tools/nope", json={"enabled": False})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete(client):
    resp = await client.post(
        "/admin/tools",
        json={"name": "d", "config": {"kind": "builtin", "function_path": "a.b.c"}},
    )
    tid = resp.json()["id"]

    resp = await client.delete(f"/admin/tools/{tid}")
    assert resp.status_code == 204

    resp = await client.get(f"/admin/tools/{tid}")
    assert resp.status_code == 404


# --- Test-tool probe dispatch -------------------------------------------


@pytest.mark.asyncio
async def test_probe_builtin_ok(client):
    """A builtin pointing at an importable function returns ok=True."""
    resp = await client.post(
        "/admin/tools",
        json={
            "name": "known",
            "config": {
                "kind": "builtin",
                "function_path": "gclaw.tools.research_tools.fetch_url",
            },
        },
    )
    tid = resp.json()["id"]

    resp = await client.post(f"/admin/tools/{tid}/test")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "latency_ms" in body
    assert body["error"] is None
    # sample_response should at minimum echo the function path / signature
    assert body["sample_response"] is not None


@pytest.mark.asyncio
async def test_probe_builtin_bad_path(client):
    """A builtin with an unimportable path returns ok=False with an error."""
    resp = await client.post(
        "/admin/tools",
        json={
            "name": "broken",
            "config": {
                "kind": "builtin",
                "function_path": "gclaw.definitely.not_a_real.path",
            },
        },
    )
    tid = resp.json()["id"]

    resp = await client.post(f"/admin/tools/{tid}/test")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]


@pytest.mark.asyncio
async def test_probe_mcp_not_yet_implemented(client):
    """Phase 2 ships the dispatch, Phase 4 wires the real MCP probe.

    Until then the endpoint must still respond cleanly (no 500) and
    mark the probe as not-yet-implemented so the UI can show a
    friendly message.
    """
    resp = await client.post(
        "/admin/tools",
        json={
            "name": "fs",
            "config": {"kind": "mcp", "transport": "stdio", "endpoint": "x"},
        },
    )
    tid = resp.json()["id"]

    resp = await client.post(f"/admin/tools/{tid}/test")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]
    # Expected pattern — later phases overwrite with real probes.
    assert "phase" in body["error"].lower()


@pytest.mark.asyncio
async def test_probe_missing_tool_returns_404(client):
    resp = await client.post("/admin/tools/nope/test")
    assert resp.status_code == 404
