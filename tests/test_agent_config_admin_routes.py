"""Admin API tests for /admin/agents CRUD."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from gclaw.api.agent_config_routes import init_agent_config_router
from gclaw.auth.dependencies import get_current_user_id
from gclaw.config.agent_config_service import AgentConfigService
from gclaw.config.loader import ConfigLoader
from gclaw.models.agent_config import AgentOverride


class FakeOverrideRepo:
    def __init__(self):
        self.store: dict[str, AgentOverride] = {}

    def create(self, o):
        self.store[o.agent_name] = o
        return o

    def get(self, name):
        return self.store.get(name)

    def update(self, o):
        self.store[o.agent_name] = o
        return o

    def delete(self, name):
        self.store.pop(name, None)

    def list_all(self):
        return list(self.store.values())


@pytest.fixture
def service(tmp_path: Path) -> AgentConfigService:
    (tmp_path / "agents").mkdir()
    (tmp_path / "soul").mkdir()
    (tmp_path / "soul" / "base.md").write_text("base")
    (tmp_path / "agents" / "dev-mgr.md").write_text("You are dev.")
    (tmp_path / "agents" / "orchestrator.md").write_text("You are root.")
    loader = ConfigLoader(str(tmp_path))
    return AgentConfigService(
        override_repo=FakeOverrideRepo(),
        loader=loader,
        skill_registry=None,
        agents_dir=tmp_path / "agents",
    )


@pytest.fixture
def app(service):
    app = FastAPI()
    app.include_router(init_agent_config_router(service))
    app.dependency_overrides[get_current_user_id] = lambda: "test_user"
    return app


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_list_agents(client):
    r = await client.get("/admin/agents")
    assert r.status_code == 200
    names = [a["name"] for a in r.json()]
    assert "dev-mgr" in names and "orchestrator" in names


@pytest.mark.asyncio
async def test_get_agent_effective(client):
    r = await client.get("/admin/agents/dev-mgr")
    assert r.status_code == 200
    assert r.json()["body"].startswith("You are dev.")


@pytest.mark.asyncio
async def test_get_agent_404(client):
    r = await client.get("/admin/agents/nope")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_patch_and_read_override(client):
    r = await client.patch(
        "/admin/agents/dev-mgr",
        json={"identity": {"display_name": "Dev!"}},
    )
    assert r.status_code == 200
    r = await client.get("/admin/agents/dev-mgr/override")
    assert r.status_code == 200
    assert r.json()["identity"]["display_name"] == "Dev!"


@pytest.mark.asyncio
async def test_get_override_404(client):
    r = await client.get("/admin/agents/dev-mgr/override")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_create_standalone(client):
    r = await client.post("/admin/agents", json={
        "agent_name": "my-bot",
        "body": "Hi!",
        "display_name": "MyBot",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["is_standalone"] is True

    # Duplicate should fail
    r2 = await client.post("/admin/agents", json={
        "agent_name": "my-bot", "body": "again",
    })
    assert r2.status_code == 400


@pytest.mark.asyncio
async def test_delete_protected_requires_force(client):
    r = await client.delete("/admin/agents/orchestrator")
    assert r.status_code == 409

    r2 = await client.delete("/admin/agents/orchestrator?force=true")
    assert r2.status_code == 200


@pytest.mark.asyncio
async def test_delete_non_protected(client):
    # Create a standalone agent so we can delete its override cleanly.
    await client.post("/admin/agents", json={
        "agent_name": "scratch-agent", "body": "hi",
    })
    r = await client.delete("/admin/agents/scratch-agent")
    assert r.status_code == 200
    body = r.json()
    assert body["deleted"] is True
    assert body["reverted_to_baseline"] is False


@pytest.mark.asyncio
async def test_baseline_endpoint(client):
    r = await client.get("/admin/agents/dev-mgr/baseline")
    assert r.status_code == 200
    assert "You are dev." in r.json()["content"]

    r2 = await client.get("/admin/agents/nope/baseline")
    assert r2.status_code == 404
