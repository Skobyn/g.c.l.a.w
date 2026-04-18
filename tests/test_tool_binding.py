"""Tests for ToolBindingService — catalog IDs → ADK-ready callables."""

from __future__ import annotations

import pytest

from gclaw.tools.catalog.binding import ToolBindingService
from gclaw.tools.catalog.builtin_registry import (
    clear_registry_for_tests,
    get_registered,
    tool_export,
)
from gclaw.tools.catalog.models import (
    BuiltinConfig,
    CodeExecConfig,
    McpConfig,
)
from gclaw.tools.catalog.service import ToolCatalogService
from tests._tool_catalog_fakes import FakeToolRepo


# Module-level tool functions so importlib can actually resolve them
# via dotted path. The registry is reset between tests, but the
# underlying functions are stable and re-registered in _register_all().


def sample_echo(x: str) -> str:
    """Return x."""
    return x


def sample_add(a: int, b: int) -> int:
    """Return a + b."""
    return a + b


@pytest.fixture(autouse=True)
def _reset_and_register():
    clear_registry_for_tests()
    yield
    clear_registry_for_tests()


def _register(func) -> str:
    """Register a module-level function via tool_export and return its path."""
    decorated = tool_export()(func)
    return get_registered()[func.__name__].function_path


@pytest.fixture
def service():
    return ToolCatalogService(tool_repo=FakeToolRepo())


@pytest.fixture
def binding(service):
    return ToolBindingService(catalog_service=service)


# --- resolve_catalog_tools ----------------------------------------------


def test_resolve_empty_ids_returns_empty(binding):
    assert binding.resolve_catalog_tools([]) == []


def test_resolve_builtin_returns_callable(binding, service):
    path = _register(sample_echo)
    rec = service.create_tool(
        name="echo", config=BuiltinConfig(function_path=path)
    )
    tools = binding.resolve_catalog_tools([rec.id])
    assert len(tools) == 1
    assert callable(tools[0])
    assert tools[0]("hello") == "hello"


def test_resolve_skips_disabled(binding, service):
    path = _register(sample_echo)
    rec = service.create_tool(
        name="echo",
        config=BuiltinConfig(function_path=path),
        enabled=False,
    )
    assert binding.resolve_catalog_tools([rec.id]) == []


def test_resolve_missing_id_skipped(binding, service):
    path = _register(sample_echo)
    rec = service.create_tool(
        name="echo", config=BuiltinConfig(function_path=path)
    )
    result = binding.resolve_catalog_tools([rec.id, "tool_does_not_exist"])
    assert len(result) == 1


def test_resolve_bad_function_path_skipped(binding, service):
    rec = service.create_tool(
        name="broken",
        config=BuiltinConfig(function_path="gclaw.not.real.function"),
    )
    # Binding must not raise — a broken builtin becomes a silent skip.
    assert binding.resolve_catalog_tools([rec.id]) == []


def test_resolve_non_builtin_kinds_skipped_for_now(binding, service):
    """Phase 3 only wires builtins. MCP / HTTP / code_exec become
    usable in later phases — until then they're silently skipped."""
    rec_mcp = service.create_tool(
        name="mcp", config=McpConfig(transport="stdio", endpoint="x")
    )
    rec_code = service.create_tool(
        name="code", config=CodeExecConfig(runtime="python3.12")
    )
    assert binding.resolve_catalog_tools([rec_mcp.id, rec_code.id]) == []


def test_resolve_preserves_order(binding, service):
    p1 = _register(sample_echo)
    p2 = _register(sample_add)
    r1 = service.create_tool(name="echo", config=BuiltinConfig(function_path=p1))
    r2 = service.create_tool(name="add", config=BuiltinConfig(function_path=p2))
    tools = binding.resolve_catalog_tools([r2.id, r1.id])
    assert [t.__name__ for t in tools] == ["sample_add", "sample_echo"]
