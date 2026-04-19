"""Tests for ToolCatalogService — CRUD on top of the repo fake."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from gclaw.tools.catalog.models import (
    BuiltinConfig,
    CodeExecConfig,
    McpConfig,
    ToolKind,
    ToolRecord,
)
from gclaw.tools.catalog.service import ToolCatalogService
from _tool_catalog_fakes import FakeToolRepo


@pytest.fixture
def service() -> ToolCatalogService:
    return ToolCatalogService(tool_repo=FakeToolRepo())


# --- Create --------------------------------------------------------------

def test_create_builtin(service):
    rec = service.create_tool(
        name="web_search",
        config=BuiltinConfig(function_path="gclaw.tools.research_tools.web_search"),
    )
    assert rec.id.startswith("tool_")
    assert rec.kind == ToolKind.BUILTIN
    assert service.get_tool(rec.id) is not None


def test_create_mcp_with_credential(service):
    rec = service.create_tool(
        name="fs",
        config=McpConfig(transport="stdio", endpoint="npx fs-mcp"),
        credential_ref="projects/p/secrets/s/versions/latest",
    )
    assert rec.kind == ToolKind.MCP
    assert rec.credential_ref == "projects/p/secrets/s/versions/latest"


def test_create_rejects_dict_with_wrong_shape(service):
    """Passing a dict that fails the discriminated-union validation
    must raise — never silently accept a malformed config."""
    with pytest.raises((ValidationError, ValueError)):
        service.create_tool(
            name="broken",
            config={"kind": "mcp", "no_endpoint_or_transport": True},
        )


# --- Get / list ----------------------------------------------------------

def test_list_empty(service):
    assert service.list_tools() == []


def test_list_all_and_filter_enabled(service):
    a = service.create_tool(
        name="a",
        config=BuiltinConfig(function_path="x.y.a"),
    )
    b = service.create_tool(
        name="b",
        config=BuiltinConfig(function_path="x.y.b"),
        enabled=False,
    )
    assert {t.id for t in service.list_tools()} == {a.id, b.id}
    assert [t.id for t in service.list_enabled()] == [a.id]


def test_list_by_kind(service):
    b = service.create_tool(name="b", config=BuiltinConfig(function_path="x.y.b"))
    m = service.create_tool(name="m", config=McpConfig(transport="http", endpoint="https://x"))
    builtins = service.list_by_kind(ToolKind.BUILTIN)
    mcps = service.list_by_kind(ToolKind.MCP)
    assert [t.id for t in builtins] == [b.id]
    assert [t.id for t in mcps] == [m.id]


def test_get_missing_returns_none(service):
    assert service.get_tool("nope") is None


# --- Update --------------------------------------------------------------

def test_update_toggles_enabled(service):
    rec = service.create_tool(name="x", config=BuiltinConfig(function_path="x.y.z"))
    updated = service.update_tool(rec.id, enabled=False)
    assert updated.enabled is False
    assert service.get_tool(rec.id).enabled is False


def test_update_rename(service):
    rec = service.create_tool(name="old", config=BuiltinConfig(function_path="x.y.z"))
    updated = service.update_tool(rec.id, name="new")
    assert updated.name == "new"


def test_update_replaces_config(service):
    rec = service.create_tool(
        name="t", config=BuiltinConfig(function_path="x.y.z")
    )
    new_cfg = McpConfig(transport="sse", endpoint="https://x")
    updated = service.update_tool(rec.id, config=new_cfg)
    assert updated.kind == ToolKind.MCP
    assert isinstance(updated.config, McpConfig)


def test_update_missing_raises(service):
    with pytest.raises(ValueError):
        service.update_tool("nope", enabled=False)


def test_update_ignores_reserved_fields(service):
    rec = service.create_tool(
        name="t", config=BuiltinConfig(function_path="x.y.z")
    )
    original_id = rec.id
    original_created = rec.created_at
    # id / created_at are immutable — silently dropped from the update payload.
    updated = service.update_tool(rec.id, id="hacked", created_at="not-a-date")
    assert updated.id == original_id
    assert updated.created_at == original_created


# --- Delete --------------------------------------------------------------

def test_delete_removes(service):
    rec = service.create_tool(name="d", config=BuiltinConfig(function_path="a.b.c"))
    service.delete_tool(rec.id)
    assert service.get_tool(rec.id) is None
    assert service.list_tools() == []


def test_delete_missing_is_silent(service):
    # Repo fake silently no-ops; service mirrors that contract.
    service.delete_tool("nope")


# --- Validation helper ---------------------------------------------------

def test_validate_config_accepts_valid_dict(service):
    valid = {
        "kind": "code_exec",
        "runtime": "python3.12",
        "timeout_seconds": 5,
    }
    cfg = service.validate_config(valid)
    assert isinstance(cfg, CodeExecConfig)
    assert cfg.timeout_seconds == 5


def test_validate_config_rejects_wrong_keys(service):
    bad = {"kind": "mcp", "endpoint": "x"}  # missing required transport
    with pytest.raises((ValidationError, ValueError)):
        service.validate_config(bad)
