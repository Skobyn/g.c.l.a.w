"""POST /chat routes to the right AgentRunner based on agent_name.

These tests exercise the full ASGI path through FastAPI so we catch
any wiring bug in init_chat_router + the AgentRunnerRegistry handoff.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock
from httpx import AsyncClient, ASGITransport

from gclaw.api.app import create_app
from gclaw.auth.dependencies import get_current_user_id
from gclaw.dispatch.runner import AgentResponse
from gclaw.dispatch.runner_registry import AgentRunnerRegistry


async def _override_user_id() -> str:
    return "test_user_1"


@pytest.fixture
def board_service():
    svc = MagicMock()
    svc.get_all_tasks.return_value = []
    return svc


@pytest.fixture
def runners():
    """Build a dict of pre-seeded AsyncMock runners keyed by agent name."""
    rs: dict[str, AsyncMock] = {}
    for name in ("orchestrator", "intel", "content-scott"):
        r = AsyncMock()
        r.run.return_value = AgentResponse(
            text=f"hello from {name}", is_final=True
        )
        r.end_session = AsyncMock(return_value=None)
        rs[name] = r
    return rs


@pytest.fixture
def registry(runners):
    """AgentRunnerRegistry backed by the fixture runners.

    The builder raises if asked for a name we didn't pre-seed — makes
    wiring bugs loud instead of silently building a stub.
    """

    def builder(name: str):
        if name not in runners:
            raise KeyError(f"unexpected agent {name!r}")
        return runners[name]

    reg = AgentRunnerRegistry(default_agent="orchestrator", builder=builder)
    for name, r in runners.items():
        reg.register(name, r)
    return reg


@pytest.fixture
def app(board_service, runners, registry):
    application = create_app(
        board_service=board_service,
        agent_runner=runners["orchestrator"],
        agent_runner_registry=registry,
    )
    application.dependency_overrides[get_current_user_id] = _override_user_id
    return application


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_chat_without_agent_name_hits_orchestrator(client, runners):
    """Back-compat: legacy body (no agent_name) routes to orchestrator."""
    resp = await client.post(
        "/chat", json={"session_id": "sess_1", "message": "hi"}
    )
    assert resp.status_code == 200
    assert resp.json()["text"] == "hello from orchestrator"

    runners["orchestrator"].run.assert_awaited_once()
    runners["intel"].run.assert_not_awaited()
    runners["content-scott"].run.assert_not_awaited()


@pytest.mark.asyncio
async def test_chat_with_null_agent_name_hits_orchestrator(client, runners):
    resp = await client.post(
        "/chat",
        json={"session_id": "sess_1", "message": "hi", "agent_name": None},
    )
    assert resp.status_code == 200
    runners["orchestrator"].run.assert_awaited_once()
    runners["intel"].run.assert_not_awaited()


@pytest.mark.asyncio
async def test_chat_with_named_agent_routes_to_that_runner(client, runners):
    resp = await client.post(
        "/chat",
        json={
            "session_id": "sess_1",
            "message": "what are you up to?",
            "agent_name": "intel",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["text"] == "hello from intel"

    runners["intel"].run.assert_awaited_once()
    runners["orchestrator"].run.assert_not_awaited()
    runners["content-scott"].run.assert_not_awaited()


@pytest.mark.asyncio
async def test_chat_orchestrator_uses_unscoped_session_id(client, runners):
    """The default (orchestrator) path keeps the raw session_id so
    existing clients + persistent session stores keep working."""
    await client.post(
        "/chat", json={"session_id": "sess_legacy", "message": "hi"}
    )
    kwargs = runners["orchestrator"].run.await_args.kwargs
    assert kwargs["session_id"] == "sess_legacy"


@pytest.mark.asyncio
async def test_chat_named_agent_uses_scoped_session_id(client, runners):
    """Non-default agents get a session_id suffixed with the agent
    name so ADK's session state doesn't leak between agents."""
    await client.post(
        "/chat",
        json={
            "session_id": "sess_1",
            "message": "status?",
            "agent_name": "content-scott",
        },
    )
    kwargs = runners["content-scott"].run.await_args.kwargs
    assert kwargs["session_id"] == "sess_1::content-scott"


@pytest.mark.asyncio
async def test_chat_end_routes_to_named_agent(client, runners):
    resp = await client.post(
        "/chat/end",
        json={"session_id": "sess_1", "agent_name": "intel"},
    )
    assert resp.status_code == 204
    runners["intel"].end_session.assert_awaited_once_with(
        user_id="test_user_1", session_id="sess_1::intel"
    )
    runners["orchestrator"].end_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_chat_end_without_agent_name_hits_orchestrator(client, runners):
    resp = await client.post("/chat/end", json={"session_id": "sess_1"})
    assert resp.status_code == 204
    runners["orchestrator"].end_session.assert_awaited_once_with(
        user_id="test_user_1", session_id="sess_1"
    )


@pytest.mark.asyncio
async def test_chat_lazy_builds_new_agents_on_demand(board_service):
    """Agents that weren't pre-seeded should be lazily built via the
    registry's builder on first use — we don't have to register every
    known agent up front."""
    built: list[str] = []

    def builder(name: str):
        built.append(name)
        r = AsyncMock()
        r.run.return_value = AgentResponse(
            text=f"fresh-{name}", is_final=True
        )
        return r

    reg = AgentRunnerRegistry(default_agent="orchestrator", builder=builder)
    # Pre-seed only the orchestrator so the default path skips the builder.
    orchestrator = AsyncMock()
    orchestrator.run.return_value = AgentResponse(text="orc", is_final=True)
    reg.register("orchestrator", orchestrator)

    app = create_app(
        board_service=board_service,
        agent_runner=orchestrator,
        agent_runner_registry=reg,
    )
    app.dependency_overrides[get_current_user_id] = _override_user_id

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/chat",
            json={
                "session_id": "sess_1",
                "message": "hi",
                "agent_name": "dev-mgr",
            },
        )

    assert resp.status_code == 200
    assert resp.json()["text"] == "fresh-dev-mgr"
    assert built == ["dev-mgr"]
    assert "dev-mgr" in reg.loaded()
