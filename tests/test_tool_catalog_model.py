"""Tests for the Tool Catalog pydantic models.

Covers the discriminated-union config + ToolRecord round-trip shape
against the same patterns the existing ModelCatalog follows.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from gclaw.tools.catalog.models import (
    ApiKeyAuth,
    BasicAuth,
    BearerAuth,
    BuiltinConfig,
    CodeExecConfig,
    HttpApiConfig,
    McpConfig,
    NoAuth,
    OAuth2BearerAuth,
    ToolKind,
    ToolRecord,
)


# --- Kind enum -----------------------------------------------------------

def test_tool_kind_values():
    assert ToolKind.BUILTIN.value == "builtin"
    assert ToolKind.MCP.value == "mcp"
    assert ToolKind.HTTP_API.value == "http_api"
    assert ToolKind.CODE_EXEC.value == "code_exec"


# --- Builtin config ------------------------------------------------------

def test_builtin_config_round_trip():
    cfg = BuiltinConfig(function_path="gclaw.tools.research_tools.web_search")
    record = ToolRecord(name="web_search", config=cfg)
    d = record.to_firestore_dict()
    assert "id" not in d
    assert d["config"]["kind"] == "builtin"
    restored = ToolRecord.from_firestore_dict(record.id, d)
    assert restored.id == record.id
    assert restored.kind == ToolKind.BUILTIN
    assert restored.config.function_path == cfg.function_path


def test_builtin_config_missing_function_path_fails():
    with pytest.raises(ValidationError):
        BuiltinConfig()  # type: ignore[call-arg]


# --- MCP config ----------------------------------------------------------

def test_mcp_config_round_trip_stdio():
    cfg = McpConfig(
        transport="stdio",
        endpoint="npx -y @modelcontextprotocol/server-filesystem /tmp",
        allowed_tools=["read_file", "list_directory"],
        env={"FS_ROOT": "/tmp"},
    )
    record = ToolRecord(name="fs", config=cfg, credential_ref="projects/p/secrets/s/versions/latest")
    d = record.to_firestore_dict()
    assert d["config"]["kind"] == "mcp"
    assert d["config"]["transport"] == "stdio"
    restored = ToolRecord.from_firestore_dict(record.id, d)
    assert restored.kind == ToolKind.MCP
    assert restored.config.allowed_tools == ["read_file", "list_directory"]
    assert restored.config.env == {"FS_ROOT": "/tmp"}
    assert restored.credential_ref == "projects/p/secrets/s/versions/latest"


def test_mcp_config_defaults():
    cfg = McpConfig(transport="sse", endpoint="https://mcp.example.com/sse")
    assert cfg.allowed_tools is None  # no filter = all tools
    assert cfg.env == {}


def test_mcp_invalid_transport_fails():
    with pytest.raises(ValidationError):
        McpConfig(transport="smtp", endpoint="x")  # type: ignore[arg-type]


# --- HTTP API config -----------------------------------------------------

def test_http_api_round_trip_bearer():
    cfg = HttpApiConfig(
        spec_url="https://petstore.swagger.io/v2/swagger.json",
        base_url="https://petstore.swagger.io/v2",
        auth=BearerAuth(credential_ref="projects/p/secrets/petstore-token/versions/latest"),
        allowed_operations=["getPetById", "findPetsByStatus"],
    )
    record = ToolRecord(name="petstore", config=cfg)
    d = record.to_firestore_dict()
    assert d["config"]["kind"] == "http_api"
    assert d["config"]["auth"]["kind"] == "bearer"
    restored = ToolRecord.from_firestore_dict(record.id, d)
    assert restored.kind == ToolKind.HTTP_API
    assert isinstance(restored.config.auth, BearerAuth)


def test_http_api_all_auth_shapes():
    spec = "https://x/openapi.json"

    # apiKey header
    cfg = HttpApiConfig(
        spec_url=spec,
        base_url="https://x",
        auth=ApiKeyAuth(location="header", param_name="X-API-Key", credential_ref="r"),
    )
    assert cfg.auth.kind == "api_key"
    assert cfg.auth.location == "header"

    # apiKey query
    cfg = HttpApiConfig(
        spec_url=spec,
        base_url="https://x",
        auth=ApiKeyAuth(location="query", param_name="apikey", credential_ref="r"),
    )
    assert cfg.auth.location == "query"

    # basic
    cfg = HttpApiConfig(spec_url=spec, base_url="https://x", auth=BasicAuth(credential_ref="r"))
    assert cfg.auth.kind == "basic"

    # oauth2
    cfg = HttpApiConfig(spec_url=spec, base_url="https://x", auth=OAuth2BearerAuth(credential_ref="r"))
    assert cfg.auth.kind == "oauth2"

    # none
    cfg = HttpApiConfig(spec_url=spec, base_url="https://x", auth=NoAuth())
    assert cfg.auth.kind == "none"


def test_http_api_requires_spec():
    # Neither spec_url nor spec_inline should fail validation
    with pytest.raises(ValidationError):
        HttpApiConfig(base_url="https://x", auth=NoAuth())


def test_http_api_inline_spec_ok():
    cfg = HttpApiConfig(
        spec_inline={"openapi": "3.0.0", "info": {"title": "t", "version": "1"}, "paths": {}},
        base_url="https://x",
        auth=NoAuth(),
    )
    assert cfg.spec_url is None
    assert cfg.spec_inline["openapi"] == "3.0.0"


# --- Code exec config ----------------------------------------------------

def test_code_exec_config_round_trip():
    cfg = CodeExecConfig(
        runtime="python3.12",
        timeout_seconds=10,
        memory_mb=128,
        network="none",
        allowed_modules=["json", "math"],
    )
    record = ToolRecord(name="sandbox", config=cfg)
    d = record.to_firestore_dict()
    assert d["config"]["kind"] == "code_exec"
    restored = ToolRecord.from_firestore_dict(record.id, d)
    assert restored.kind == ToolKind.CODE_EXEC
    assert restored.config.timeout_seconds == 10
    assert restored.config.network == "none"


def test_code_exec_defaults():
    cfg = CodeExecConfig(runtime="python3.12")
    assert cfg.timeout_seconds == 30
    assert cfg.memory_mb == 256
    assert cfg.network == "none"
    assert cfg.allowed_modules == []


def test_code_exec_invalid_runtime_fails():
    with pytest.raises(ValidationError):
        CodeExecConfig(runtime="node18")  # type: ignore[arg-type]


# --- Discriminated-union coercion ---------------------------------------

def test_config_dict_discriminates_on_kind():
    """Parsing a ToolRecord from a dict should pick the right config type."""
    raw = {
        "id": "t1",
        "name": "fs",
        "config": {
            "kind": "mcp",
            "transport": "stdio",
            "endpoint": "x",
        },
        "created_at": "2026-04-18T00:00:00+00:00",
        "updated_at": "2026-04-18T00:00:00+00:00",
    }
    record = ToolRecord.model_validate(raw)
    assert record.kind == ToolKind.MCP
    assert isinstance(record.config, McpConfig)


def test_config_dict_unknown_kind_fails():
    raw = {
        "id": "t2",
        "name": "bad",
        "config": {"kind": "pretend-tool", "anything": "goes"},
        "created_at": "2026-04-18T00:00:00+00:00",
        "updated_at": "2026-04-18T00:00:00+00:00",
    }
    with pytest.raises(ValidationError):
        ToolRecord.model_validate(raw)
