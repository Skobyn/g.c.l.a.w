"""Tests for MCP connection-param construction and credential substitution."""

from __future__ import annotations

import pytest

from gclaw.tools.catalog.models import McpConfig
from gclaw.tools.mcp.client import (
    build_connection_params,
    resolve_env_with_credential,
)


# --- Env substitution ---------------------------------------------------


def test_resolve_env_passthrough_when_no_credential():
    env = {"FS_ROOT": "/tmp", "LOG_LEVEL": "info"}
    out = resolve_env_with_credential(env, credential_value=None)
    assert out == env


def test_resolve_env_substitutes_sentinel():
    env = {"GITHUB_TOKEN": "${CREDENTIAL}", "EDITOR": "vim"}
    out = resolve_env_with_credential(env, credential_value="ghp_secret")
    assert out["GITHUB_TOKEN"] == "ghp_secret"
    assert out["EDITOR"] == "vim"


def test_resolve_env_multiple_sentinels():
    env = {"A": "${CREDENTIAL}", "B": "${CREDENTIAL}"}
    out = resolve_env_with_credential(env, credential_value="X")
    assert out == {"A": "X", "B": "X"}


def test_resolve_env_noop_when_sentinel_missing_credential():
    env = {"GITHUB_TOKEN": "${CREDENTIAL}"}
    # No credential → the sentinel stays as-is; the caller can decide
    # whether to refuse to connect.
    out = resolve_env_with_credential(env, credential_value=None)
    assert out["GITHUB_TOKEN"] == "${CREDENTIAL}"


# --- Connection param construction --------------------------------------


def test_stdio_params_parses_command_and_args():
    cfg = McpConfig(
        transport="stdio",
        endpoint="npx -y @modelcontextprotocol/server-filesystem /tmp",
        env={"FS_ROOT": "/tmp"},
    )
    params = build_connection_params(cfg, resolved_env=cfg.env)
    from google.adk.tools.mcp_tool import StdioConnectionParams
    assert isinstance(params, StdioConnectionParams)
    server = params.server_params
    assert server.command == "npx"
    assert server.args == ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    assert server.env == {"FS_ROOT": "/tmp"}


def test_stdio_params_command_only():
    cfg = McpConfig(transport="stdio", endpoint="my-mcp-server")
    params = build_connection_params(cfg, resolved_env={})
    from google.adk.tools.mcp_tool import StdioConnectionParams
    assert isinstance(params, StdioConnectionParams)
    assert params.server_params.command == "my-mcp-server"
    assert params.server_params.args == []


def test_sse_params_from_endpoint():
    cfg = McpConfig(
        transport="sse",
        endpoint="https://mcp.example.com/sse",
        env={"Authorization": "Bearer abc"},
    )
    params = build_connection_params(cfg, resolved_env=cfg.env)
    from google.adk.tools.mcp_tool import SseConnectionParams
    assert isinstance(params, SseConnectionParams)
    assert params.url == "https://mcp.example.com/sse"
    # env values become HTTP headers for SSE/HTTP transports.
    assert params.headers == {"Authorization": "Bearer abc"}


def test_http_params_from_endpoint():
    cfg = McpConfig(
        transport="http",
        endpoint="https://mcp.example.com/",
    )
    params = build_connection_params(cfg, resolved_env={})
    from google.adk.tools.mcp_tool import StreamableHTTPConnectionParams
    assert isinstance(params, StreamableHTTPConnectionParams)
    assert params.url == "https://mcp.example.com/"


def test_unknown_transport_raises():
    # Pydantic blocks unknown transports at config build — the param
    # builder mirrors that via a terminal assertion in case a caller
    # somehow constructs a stale/raw config.
    class _FakeCfg:
        transport = "carrier_pigeon"
        endpoint = "x"
        env = {}

    with pytest.raises(ValueError):
        build_connection_params(_FakeCfg(), resolved_env={})
