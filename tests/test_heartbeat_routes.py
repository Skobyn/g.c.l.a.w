"""Tests for heartbeat API endpoint."""

import pytest
from unittest.mock import MagicMock, AsyncMock
from httpx import AsyncClient, ASGITransport

from gclaw.api.app import create_app
from gclaw.dispatch.runner import AgentResponse


@pytest.fixture
def board_service():
    svc = MagicMock()
    svc.get_all_tasks.return_value = []
    return svc


@pytest.fixture
def agent_runner():
    return AsyncMock()


@pytest.fixture
def cron_service():
    return MagicMock()


@pytest.fixture
def heartbeat_service():
    svc = AsyncMock()
    svc.run.return_value = {
        "orchestrator_response": "All quiet. Nothing to do.",
        "actions_taken": [],
        "tasks_created": [],
        "context": {
            "current_time": "2026-03-30T12:00:00+00:00",
            "board_summary": {
                "total_tasks": 0,
                "backlog": 0,
                "queued": 0,
                "in_progress": 0,
                "needs_approval": 0,
                "done": 0,
                "failed": 0,
            },
            "failed_tasks": [],
            "pending_approvals": [],
            "stale_tasks": [],
            "cron_summary": {"total_crons": 0},
            "memories": [],
        },
    }
    return svc


@pytest.fixture
def app(board_service, agent_runner, cron_service, heartbeat_service):
    return create_app(
        board_service=board_service,
        agent_runner=agent_runner,
        cron_service=cron_service,
        heartbeat_service=heartbeat_service,
    )


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_trigger_heartbeat(client, heartbeat_service):
    resp = await client.post("/heartbeat")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert "orchestrator_response" in data
    heartbeat_service.run.assert_called_once()


@pytest.mark.asyncio
async def test_trigger_heartbeat_with_actions(client, heartbeat_service):
    heartbeat_service.run.return_value = {
        "orchestrator_response": "Retrying failed task t3.",
        "actions_taken": ["create_board_task({'title': 'Retry: t3', 'assignee': 'dev-mgr'})"],
        "tasks_created": ["Retry: t3"],
        "context": {"board_summary": {"total_tasks": 2}},
    }

    resp = await client.post("/heartbeat")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert len(data["actions_taken"]) == 1
    assert len(data["tasks_created"]) == 1


@pytest.mark.asyncio
async def test_trigger_heartbeat_error(client, heartbeat_service):
    heartbeat_service.run.side_effect = RuntimeError("Agent failed")
    resp = await client.post("/heartbeat")
    assert resp.status_code == 500
    data = resp.json()
    assert "error" in data["detail"].lower() or "failed" in data["detail"].lower()
