"""Tests for McpClientManager — caching, probe, credential resolution."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gclaw.tools.catalog.models import McpConfig, ToolRecord
from gclaw.tools.mcp.manager import McpClientManager


def _record(**overrides) -> ToolRecord:
    base = {
        "name": "fs",
        "config": McpConfig(transport="stdio", endpoint="npx fs-mcp"),
    }
    base.update(overrides)
    return ToolRecord(**base)


def test_get_toolset_caches_per_record_id():
    """Subsequent lookups with the same tool id return the same toolset."""
    mgr = McpClientManager(secret_resolver=lambda ref: None)

    fake_toolset = MagicMock(name="toolset")
    with patch(
        "gclaw.tools.mcp.manager.McpToolset",
        return_value=fake_toolset,
    ) as ctor:
        rec = _record()
        t1 = mgr.get_toolset(rec)
        t2 = mgr.get_toolset(rec)
        assert t1 is t2
        assert ctor.call_count == 1  # ctor ran exactly once


def test_get_toolset_applies_allowed_tools_as_filter():
    mgr = McpClientManager(secret_resolver=lambda ref: None)
    rec = _record(
        config=McpConfig(
            transport="stdio",
            endpoint="npx fs-mcp",
            allowed_tools=["read_file", "list_directory"],
        )
    )
    with patch("gclaw.tools.mcp.manager.McpToolset") as ctor:
        mgr.get_toolset(rec)
        kwargs = ctor.call_args.kwargs
        assert kwargs["tool_filter"] == ["read_file", "list_directory"]


def test_credential_resolver_called_with_ref():
    calls: list[str] = []

    def _resolver(ref):
        calls.append(ref)
        return "resolved-secret"

    mgr = McpClientManager(secret_resolver=_resolver)
    rec = _record(
        credential_ref="projects/p/secrets/s/versions/latest",
        config=McpConfig(
            transport="stdio",
            endpoint="npx fs-mcp",
            env={"GITHUB_TOKEN": "${CREDENTIAL}"},
        ),
    )
    with patch("gclaw.tools.mcp.manager.McpToolset"):
        mgr.get_toolset(rec)
    assert calls == ["projects/p/secrets/s/versions/latest"]


def test_credential_substitution_reaches_server_env():
    mgr = McpClientManager(secret_resolver=lambda ref: "ghp_real")
    rec = _record(
        credential_ref="ref",
        config=McpConfig(
            transport="stdio",
            endpoint="npx fs-mcp",
            env={"GITHUB_TOKEN": "${CREDENTIAL}"},
        ),
    )
    with patch("gclaw.tools.mcp.manager.McpToolset") as ctor:
        mgr.get_toolset(rec)
        params = ctor.call_args.kwargs["connection_params"]
        assert params.server_params.env == {"GITHUB_TOKEN": "ghp_real"}


@pytest.mark.asyncio
async def test_probe_returns_tool_names_and_closes():
    fake_toolset = MagicMock(name="toolset")
    # ADK MCPToolset.get_tools is async and returns BaseTool objects with .name.
    fake_tools = [MagicMock(name=f"t{i}") for i in range(3)]
    for i, t in enumerate(fake_tools):
        t.name = f"tool_{i}"
    fake_toolset.get_tools = AsyncMock(return_value=fake_tools)
    fake_toolset.close = AsyncMock()

    mgr = McpClientManager(secret_resolver=lambda ref: None)
    with patch("gclaw.tools.mcp.manager.McpToolset", return_value=fake_toolset):
        result = await mgr.probe(_record())

    assert result["ok"] is True
    assert result["tools"] == ["tool_0", "tool_1", "tool_2"]
    # Probe must close the toolset even on success so we don't leak
    # subprocesses across repeated test clicks.
    fake_toolset.close.assert_called_once()


@pytest.mark.asyncio
async def test_probe_returns_error_on_connect_failure():
    fake_toolset = MagicMock(name="toolset")
    fake_toolset.get_tools = AsyncMock(side_effect=RuntimeError("boom"))
    fake_toolset.close = AsyncMock()

    mgr = McpClientManager(secret_resolver=lambda ref: None)
    with patch("gclaw.tools.mcp.manager.McpToolset", return_value=fake_toolset):
        result = await mgr.probe(_record())

    assert result["ok"] is False
    assert "boom" in result["error"]
    # And we still close the toolset so a bad config doesn't orphan it.
    fake_toolset.close.assert_called_once()


@pytest.mark.asyncio
async def test_close_all_awaits_each_cached_toolset():
    t1 = MagicMock()
    t1.close = AsyncMock()
    t2 = MagicMock()
    t2.close = AsyncMock()

    mgr = McpClientManager(secret_resolver=lambda ref: None)
    # Seed the cache directly with our fakes — bypasses the real ctor
    # path that would need patching twice.
    mgr._cache["a"] = t1
    mgr._cache["b"] = t2

    await mgr.close_all()
    t1.close.assert_called_once()
    t2.close.assert_called_once()
    assert mgr._cache == {}
