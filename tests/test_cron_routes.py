"""Tests for cron API endpoints."""

import pytest
from unittest.mock import MagicMock
from httpx import AsyncClient, ASGITransport

from gclaw.api.app import create_app
from gclaw.models.cron import (
    AgentTurnPayload,
    Cron,
    CronExprSchedule,
    CronMode,
    CronStatus,
)
from gclaw.models.task import BoardTask, TaskStatus


def _cron(**kw):
    base = dict(
        title="C",
        assignee="dev-mgr",
        schedule=CronExprSchedule(expr="0 8 * * *"),
        payload=AgentTurnPayload(message="do"),
    )
    base.update(kw)
    return Cron(**base)


@pytest.fixture
def board_service():
    svc = MagicMock()
    svc.get_all_tasks.return_value = []
    return svc


@pytest.fixture
def agent_runner():
    from unittest.mock import AsyncMock
    return AsyncMock()


@pytest.fixture
def cron_service():
    from unittest.mock import AsyncMock
    svc = MagicMock()
    # execute() is async now
    svc.execute = AsyncMock()
    return svc


@pytest.fixture
def heartbeat_service():
    return None


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
async def test_trigger_cron(client, cron_service):
    cron_service.execute.return_value = BoardTask(
        title="Morning briefing",
        assignee="workspace-mgr",
        status=TaskStatus.BACKLOG,
    )
    resp = await client.post("/crons/cron_abc/trigger")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "triggered"
    assert data["cron_id"] == "cron_abc"
    cron_service.execute.assert_called_once_with("cron_abc")


@pytest.mark.asyncio
async def test_trigger_nonexistent_cron(client, cron_service):
    cron_service.execute.side_effect = ValueError("Cron cron_nope not found")
    resp = await client.post("/crons/cron_nope/trigger")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_trigger_paused_cron(client, cron_service):
    cron_service.execute.side_effect = ValueError("Cron cron_1 is paused")
    resp = await client.post("/crons/cron_1/trigger")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_crons(client, cron_service):
    cron_service.list_all.return_value = [
        _cron(title="C1"),
        _cron(title="C2", assignee="workspace-mgr"),
    ]
    resp = await client.get("/crons")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["title"] == "C1"


@pytest.mark.asyncio
async def test_create_cron(client, cron_service):
    cron_service.create.side_effect = lambda **kw: _cron(
        title=kw["title"],
        assignee=kw["assignee"],
    )
    resp = await client.post("/crons", json={
        "title": "New cron",
        "schedule": "0 8 * * *",
        "assignee": "workspace-mgr",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "New cron"
    cron_service.create.assert_called_once()


@pytest.mark.asyncio
async def test_update_cron(client, cron_service):
    cron_service.update.return_value = _cron(title="Renamed")
    resp = await client.patch(
        "/crons/cron_abc",
        json={"title": "Renamed", "enabled": False},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Renamed"
    cron_service.update.assert_called_once()
    args, kwargs = cron_service.update.call_args
    assert args[0] == "cron_abc"
    assert kwargs.get("title") == "Renamed"
    assert kwargs.get("enabled") is False


@pytest.mark.asyncio
async def test_update_cron_not_found(client, cron_service):
    cron_service.update.side_effect = ValueError("Cron cron_nope not found")
    resp = await client.patch("/crons/cron_nope", json={"title": "x"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_cron(client, cron_service):
    cron_service.delete.return_value = None
    resp = await client.delete("/crons/cron_abc")
    assert resp.status_code == 204
    cron_service.delete.assert_called_once_with("cron_abc")
