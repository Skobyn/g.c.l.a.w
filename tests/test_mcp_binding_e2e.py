"""Wire-up tests: MCP catalog entry → binding → tester."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gclaw.tools.catalog.binding import ToolBindingService
from gclaw.tools.catalog.models import McpConfig
from gclaw.tools.catalog.service import ToolCatalogService
from gclaw.tools.catalog.tester import probe_tool, set_mcp_manager
from gclaw.tools.mcp.manager import McpClientManager
from tests._tool_catalog_fakes import FakeToolRepo


@pytest.fixture
def service():
    return ToolCatalogService(tool_repo=FakeToolRepo())


@pytest.fixture(autouse=True)
def _reset_tester_deps():
    """Leave the module-level probe dependencies clean between tests."""
    set_mcp_manager(None)
    yield
    set_mcp_manager(None)


def test_binding_returns_toolset_for_enabled_mcp(service):
    fake_toolset = MagicMock(name="toolset")
    mgr = McpClientManager(secret_resolver=lambda ref: None)
    with patch("gclaw.tools.mcp.manager.McpToolset", return_value=fake_toolset):
        rec = service.create_tool(
            name="fs",
            config=McpConfig(transport="stdio", endpoint="npx fs-mcp"),
        )
        binding = ToolBindingService(catalog_service=service, mcp_manager=mgr)
        tools = binding.resolve_catalog_tools([rec.id])

    # MCP yields the toolset object itself (ADK expands it at turn
    # time), not flattened tool callables.
    assert len(tools) == 1
    assert tools[0] is fake_toolset


def test_binding_mcp_without_manager_is_silent_skip(service):
    rec = service.create_tool(
        name="fs",
        config=McpConfig(transport="stdio", endpoint="npx fs-mcp"),
    )
    binding = ToolBindingService(catalog_service=service, mcp_manager=None)
    # Without a manager, MCP kind is treated like the pre-Phase-4 stub:
    # silent skip, no raise.
    assert binding.resolve_catalog_tools([rec.id]) == []


@pytest.mark.asyncio
async def test_tester_mcp_branch_uses_manager(service):
    fake_toolset = MagicMock(name="toolset")
    tool_obj = MagicMock()
    tool_obj.name = "list_directory"
    fake_toolset.get_tools = AsyncMock(return_value=[tool_obj])
    fake_toolset.close = AsyncMock()

    mgr = McpClientManager(secret_resolver=lambda ref: None)
    set_mcp_manager(mgr)

    with patch("gclaw.tools.mcp.manager.McpToolset", return_value=fake_toolset):
        rec = service.create_tool(
            name="fs",
            config=McpConfig(transport="stdio", endpoint="npx fs-mcp"),
        )
        result = await probe_tool(rec)

    assert result["ok"] is True
    assert result["error"] is None
    # sample_response must show what the server advertises.
    assert result["sample_response"] == {"tools": ["list_directory"]}


@pytest.mark.asyncio
async def test_tester_mcp_branch_without_manager_is_stub(service):
    # No manager set → Phase-2 stub shape: ok=False with a phase note.
    rec = service.create_tool(
        name="fs",
        config=McpConfig(transport="stdio", endpoint="x"),
    )
    result = await probe_tool(rec)
    assert result["ok"] is False
    assert "phase" in result["error"].lower()
