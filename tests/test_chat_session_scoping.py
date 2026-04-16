"""Session isolation between agents.

Two users talking to different agents with the same logical
``session_id`` should hit different underlying ADK session keys so
turn history does not bleed across agents.
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


def _mk_runner(tag: str) -> AsyncMock:
    r = AsyncMock()
    r.run.return_value = AgentResponse(text=f"from {tag}", is_final=True)
    return r


@pytest.mark.asyncio
async def test_sessions_do_not_leak_across_agents(board_service):
    """Same client-side session_id across two agents → distinct
    per-agent ADK session_ids so history can never cross over."""
    orch = _mk_runner("orch")
    intel = _mk_runner("intel")
    content = _mk_runner("content-scott")

    def builder(name: str):
        mapping = {"orchestrator": orch, "intel": intel, "content-scott": content}
        return mapping[name]

    reg = AgentRunnerRegistry(default_agent="orchestrator", builder=builder)
    for name, r in (
        ("orchestrator", orch),
        ("intel", intel),
        ("content-scott", content),
    ):
        reg.register(name, r)

    app = create_app(
        board_service=board_service,
        agent_runner=orch,
        agent_runner_registry=reg,
    )
    app.dependency_overrides[get_current_user_id] = _override_user_id
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await c.post(
            "/chat",
            json={
                "session_id": "shared_sess",
                "message": "msg1",
                "agent_name": "intel",
            },
        )
        await c.post(
            "/chat",
            json={
                "session_id": "shared_sess",
                "message": "msg2",
                "agent_name": "content-scott",
            },
        )
        await c.post(
            "/chat",
            json={"session_id": "shared_sess", "message": "msg3"},
        )

    intel_sid = intel.run.await_args.kwargs["session_id"]
    content_sid = content.run.await_args.kwargs["session_id"]
    orch_sid = orch.run.await_args.kwargs["session_id"]

    assert intel_sid == "shared_sess::intel"
    assert content_sid == "shared_sess::content-scott"
    # Default agent keeps the raw id — back-compat.
    assert orch_sid == "shared_sess"

    # Sanity: all three are distinct.
    assert len({intel_sid, content_sid, orch_sid}) == 3


@pytest.mark.asyncio
async def test_same_agent_reuses_same_session_id(board_service):
    """Two turns to the same agent with the same session_id should
    hit the same ADK session — history only isolates across agents,
    not across turns within an agent."""
    intel = _mk_runner("intel")
    orch = _mk_runner("orch")

    def builder(name: str):
        return {"intel": intel, "orchestrator": orch}[name]

    reg = AgentRunnerRegistry(default_agent="orchestrator", builder=builder)
    reg.register("orchestrator", orch)
    reg.register("intel", intel)

    app = create_app(
        board_service=board_service,
        agent_runner=orch,
        agent_runner_registry=reg,
    )
    app.dependency_overrides[get_current_user_id] = _override_user_id
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as c:
        for msg in ("first", "second"):
            await c.post(
                "/chat",
                json={
                    "session_id": "s",
                    "message": msg,
                    "agent_name": "intel",
                },
            )

    # Both turns on intel got the same scoped session id.
    assert intel.run.await_count == 2
    sids = [call.kwargs["session_id"] for call in intel.run.await_args_list]
    assert sids == ["s::intel", "s::intel"]


@pytest.mark.asyncio
async def test_end_session_matches_scoped_session(board_service):
    """``/chat/end`` on a specific agent only ends that agent's
    scoped session — the orchestrator session for the same raw id
    is untouched."""
    orch = _mk_runner("orch")
    orch.end_session = AsyncMock(return_value=None)
    intel = _mk_runner("intel")
    intel.end_session = AsyncMock(return_value=None)

    def builder(name: str):
        return {"orchestrator": orch, "intel": intel}[name]

    reg = AgentRunnerRegistry(default_agent="orchestrator", builder=builder)
    reg.register("orchestrator", orch)
    reg.register("intel", intel)

    app = create_app(
        board_service=board_service,
        agent_runner=orch,
        agent_runner_registry=reg,
    )
    app.dependency_overrides[get_current_user_id] = _override_user_id
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # End the intel session only.
        resp = await c.post(
            "/chat/end",
            json={"session_id": "s", "agent_name": "intel"},
        )

    assert resp.status_code == 204
    intel.end_session.assert_awaited_once_with(
        user_id="test_user_1", session_id="s::intel"
    )
    orch.end_session.assert_not_awaited()
