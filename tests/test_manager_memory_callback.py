"""Tests for per-manager agent-scoped memory recall callback.

Verifies build_managers installs a before_agent_callback on each of the
five managers when a memory_service is provided, and that the callback
correctly recalls agent-scoped memories and returns injectable Content.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from gclaw.agents.factory import AgentFactory
from gclaw.agents.orchestrator import (
    _make_memory_recall_callback,
    build_managers,
)
from gclaw.config.loader import ConfigLoader
from gclaw.models.memory import Memory


@pytest.fixture
def config_dir(tmp_path):
    soul_dir = tmp_path / "soul"
    soul_dir.mkdir()
    (soul_dir / "base.md").write_text("Base personality.\n")
    for overlay in ("workspace", "dev", "home", "comms", "research", "profile", "content"):
        (soul_dir / f"{overlay}.md").write_text(f"{overlay} overlay.\n")
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    for mgr in (
        "workspace-mgr",
        "dev-mgr",
        "home-mgr",
        "comms-mgr",
        "research-mgr",
        "profile-mgr",
        "content-mgr",
    ):
        (agents_dir / f"{mgr}.md").write_text(f"{mgr} role.\n")
    return tmp_path


@pytest.fixture
def factory(config_dir):
    return AgentFactory(
        loader=ConfigLoader(str(config_dir)),
        default_model="gemini-2.5-flash",
    )


@pytest.fixture
def memory_service():
    svc = MagicMock()
    svc.recall = AsyncMock(return_value=[
        Memory(fact="User prefers JSON over YAML", topic="USER_PREFERENCES"),
    ])
    svc.format_for_prompt = MagicMock(
        return_value="- User prefers JSON over YAML"
    )
    return svc


def _ctx(user_id: str | None, text: str | None):
    """Build a duck-typed ADK context with just what the callback reads."""
    parts = [SimpleNamespace(text=text)] if text is not None else []
    return SimpleNamespace(
        user_id=user_id,
        user_content=SimpleNamespace(parts=parts) if parts else None,
    )


# ---------------------------------------------------------------------------
# _make_memory_recall_callback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_callback_recalls_with_correct_agent_id(memory_service):
    cb = _make_memory_recall_callback(memory_service, "comms-mgr")
    ctx = _ctx(user_id="user_1", text="help me reply to this")

    result = await cb(callback_context=ctx)

    memory_service.recall.assert_awaited_once_with(
        user_id="user_1",
        query="help me reply to this",
        agent_id="comms-mgr",
        merge_user_scope=False,
    )
    assert result is not None
    assert result.role == "user"
    assert "comms-mgr" in result.parts[0].text
    assert "JSON over YAML" in result.parts[0].text


@pytest.mark.asyncio
async def test_callback_returns_none_when_no_query(memory_service):
    cb = _make_memory_recall_callback(memory_service, "dev-mgr")
    ctx = _ctx(user_id="user_1", text=None)
    result = await cb(callback_context=ctx)
    assert result is None
    memory_service.recall.assert_not_awaited()


@pytest.mark.asyncio
async def test_callback_returns_none_when_no_user_id(memory_service):
    cb = _make_memory_recall_callback(memory_service, "dev-mgr")
    ctx = _ctx(user_id=None, text="hello")
    result = await cb(callback_context=ctx)
    assert result is None
    memory_service.recall.assert_not_awaited()


@pytest.mark.asyncio
async def test_callback_returns_none_when_no_memories_found(memory_service):
    memory_service.recall = AsyncMock(return_value=[])
    cb = _make_memory_recall_callback(memory_service, "dev-mgr")
    ctx = _ctx(user_id="user_1", text="hello")
    result = await cb(callback_context=ctx)
    assert result is None


@pytest.mark.asyncio
async def test_callback_parameter_is_named_callback_context(memory_service):
    """Regression: ADK's BaseAgent enforces that the before_agent_callback
    parameter must be literally named `callback_context`. This test fails
    if anyone renames the parameter back to `ctx` (as was shipped and
    broken in commit 9829db1, caught by the live eval run)."""
    import inspect
    cb = _make_memory_recall_callback(memory_service, "workspace-mgr")
    sig = inspect.signature(cb)
    assert "callback_context" in sig.parameters


@pytest.mark.asyncio
async def test_callback_swallows_recall_exceptions(memory_service):
    memory_service.recall = AsyncMock(side_effect=RuntimeError("memory down"))
    cb = _make_memory_recall_callback(memory_service, "dev-mgr")
    ctx = _ctx(user_id="user_1", text="hello")
    # Must not raise.
    result = await cb(callback_context=ctx)
    assert result is None


# ---------------------------------------------------------------------------
# build_managers integration
# ---------------------------------------------------------------------------


def test_build_managers_installs_callbacks_when_memory_service_provided(
    factory, memory_service
):
    managers = build_managers(
        factory=factory,
        board_tools=[],
        memory_service=memory_service,
    )

    expected = {
        "workspace_mgr",
        "dev_mgr",
        "home_mgr",
        "comms_mgr",
        "research_mgr",
        "profile_mgr",
        "content_mgr",
    }
    assert set(managers.keys()) == expected

    for mgr in managers.values():
        assert mgr.before_agent_callback is not None


def test_build_managers_no_memory_service_no_callbacks(factory):
    managers = build_managers(
        factory=factory,
        board_tools=[],
        memory_service=None,
    )
    for mgr in managers.values():
        assert not mgr.before_agent_callback


@pytest.mark.asyncio
async def test_build_managers_dev_mgr_callback_uses_dev_mgr_id(
    factory, memory_service
):
    managers = build_managers(
        factory=factory,
        board_tools=[],
        memory_service=memory_service,
    )
    # before_agent_callback may be wrapped in a list by ADK internals
    cb = managers["dev_mgr"].before_agent_callback
    if isinstance(cb, list):
        cb = cb[0]

    ctx = _ctx(user_id="user_1", text="review this diff")
    await cb(callback_context=ctx)

    memory_service.recall.assert_awaited_once()
    kwargs = memory_service.recall.call_args.kwargs
    assert kwargs["agent_id"] == "dev-mgr"
