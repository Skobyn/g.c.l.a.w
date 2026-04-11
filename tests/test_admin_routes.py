"""Tests for admin API routes (agents, heartbeat logs, soul, skills, memory)."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from gclaw.api.admin_routes import init_admin_router
from gclaw.models.memory import Memory
from gclaw.models.skill import Skill


@pytest.fixture
def mock_services():
    """Create mock services for admin routes."""
    config_loader = MagicMock()
    config_loader.load_soul.return_value = "# Base Soul\nYou are helpful."
    config_loader.load_agent.return_value = "# Orchestrator\nRoute tasks."

    heartbeat_log_repo = MagicMock()
    heartbeat_log_repo.list_recent.return_value = []

    skill_registry = MagicMock()
    skill_registry.list_all.return_value = [
        Skill(name="email-drafter", description="Draft emails"),
    ]

    memory_service = AsyncMock()
    memory_service.recall.return_value = [
        Memory(fact="User prefers dark mode", topic="USER_PREFERENCES"),
    ]
    memory_service._client = AsyncMock()
    memory_service._client.list_memories.return_value = []
    memory_service._client.delete_memory.return_value = None

    cron_service = MagicMock()
    cron_service.list_all.return_value = []

    return {
        "config_loader": config_loader,
        "heartbeat_log_repo_factory": lambda uid: heartbeat_log_repo,
        "skill_registry": skill_registry,
        "memory_service": memory_service,
        "cron_service": cron_service,
    }


@pytest.fixture
def admin_app(mock_services):
    app = FastAPI()
    app.include_router(init_admin_router(**mock_services))
    # Bypass auth for tests
    from gclaw.auth.dependencies import get_current_user_id
    app.dependency_overrides[get_current_user_id] = lambda: "test_user"
    return app


@pytest.fixture
async def admin_client(admin_app):
    transport = ASGITransport(app=admin_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_list_agents(admin_client):
    resp = await admin_client.get("/admin/agents")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_get_soul_file(admin_client):
    resp = await admin_client.get("/admin/soul/base")
    assert resp.status_code == 200
    assert "content" in resp.json()


@pytest.mark.asyncio
async def test_list_skills(admin_client):
    resp = await admin_client.get("/admin/skills")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "email-drafter"


@pytest.mark.asyncio
async def test_search_memories(admin_client):
    resp = await admin_client.get("/admin/memory/search?q=dark+mode")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_heartbeat_logs(admin_client):
    resp = await admin_client.get("/admin/heartbeat-logs")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_list_memories(admin_client):
    resp = await admin_client.get("/admin/memory/list")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_wipe_my_memories_calls_service(admin_client, mock_services):
    """DELETE /admin/memory wipes every memory for the authenticated user
    and returns the count."""
    mock_services["memory_service"].wipe_user_memories = AsyncMock(return_value=7)

    resp = await admin_client.delete("/admin/memory")

    assert resp.status_code == 200
    assert resp.json() == {"status": "wiped", "deleted": 7}
    mock_services["memory_service"].wipe_user_memories.assert_awaited_once_with(
        "test_user"
    )


@pytest.mark.asyncio
async def test_list_crons(admin_client):
    resp = await admin_client.get("/admin/crons")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_toggle_cron_not_found(admin_client):
    resp = await admin_client.post("/admin/crons/nonexistent/toggle")
    assert resp.status_code == 404
