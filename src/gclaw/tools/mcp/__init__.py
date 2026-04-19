"""MCP integration for the Tool Catalog.

Public surface:
    - client.build_connection_params(config, resolved_env)
    - client.resolve_env_with_credential(env, credential_value)
    - manager.McpClientManager — connection cache + probe helper
"""

from __future__ import annotations

from gclaw.tools.mcp.client import (  # noqa: F401
    build_connection_params,
    resolve_env_with_credential,
)
from gclaw.tools.mcp.manager import McpClientManager  # noqa: F401
