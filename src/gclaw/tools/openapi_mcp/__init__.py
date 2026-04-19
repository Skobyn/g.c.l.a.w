"""OpenAPI→MCP in-process wrap.

Admin pastes an OpenAPI spec URL or inline JSON; each operation
materializes as a single async callable the agent can invoke.

Public surface:
    - loader.load_spec(HttpApiConfig) → list[OperationDef]
    - tool_builder.build_tool(op, auth, base_url, secret_resolver) → Callable
"""

from __future__ import annotations

from gclaw.tools.openapi_mcp.loader import (  # noqa: F401
    OperationDef,
    Parameter,
    load_spec,
)
from gclaw.tools.openapi_mcp.tool_builder import build_tool  # noqa: F401
