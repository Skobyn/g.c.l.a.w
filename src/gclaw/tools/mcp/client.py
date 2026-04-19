"""MCP connection-param construction.

Translates an ``McpConfig`` into the matching ADK connection-param
dataclass. Stdio transport parses ``endpoint`` as a shell command +
args; SSE/HTTP transports treat ``endpoint`` as a URL and pass ``env``
through as HTTP headers.

``${CREDENTIAL}`` is the single substitution sentinel recognized in
``env`` values — the manager resolves it to the credential_ref'd
Secret Manager value before handing the env off to the client.
"""

from __future__ import annotations

import logging
import shlex
from typing import Any

logger = logging.getLogger(__name__)


_CREDENTIAL_SENTINEL = "${CREDENTIAL}"


def resolve_env_with_credential(
    env: dict[str, str], credential_value: str | None
) -> dict[str, str]:
    """Replace every ``${CREDENTIAL}`` occurrence with the resolved value.

    When ``credential_value`` is None the sentinel is left in place —
    downstream callers can decide whether that constitutes a hard
    failure (today it does not; the server just sees a literal
    ``${CREDENTIAL}`` and presumably errors out on its own).
    """
    if credential_value is None:
        return dict(env)
    return {
        k: (credential_value if v == _CREDENTIAL_SENTINEL else v)
        for k, v in env.items()
    }


def build_connection_params(config: Any, *, resolved_env: dict[str, str]) -> Any:
    """Return the ADK connection-param object for ``config``.

    Lazy-imports the ADK MCP types so the builder stays testable in
    environments where the optional ADK MCP extras aren't installed
    (CI unit tests) — callers that don't exercise those paths won't
    pay the import cost.
    """
    from google.adk.tools.mcp_tool import (  # noqa: WPS433 — lazy by design
        SseConnectionParams,
        StdioConnectionParams,
        StreamableHTTPConnectionParams,
    )
    from mcp import StdioServerParameters

    transport = getattr(config, "transport", None)
    endpoint = getattr(config, "endpoint", "") or ""

    if transport == "stdio":
        parts = shlex.split(endpoint)
        if not parts:
            raise ValueError(
                "McpConfig.endpoint must be a non-empty command for stdio"
            )
        command, *args = parts
        return StdioConnectionParams(
            server_params=StdioServerParameters(
                command=command,
                args=args,
                env=dict(resolved_env) if resolved_env else None,
            ),
        )

    if transport == "sse":
        return SseConnectionParams(
            url=endpoint,
            headers=dict(resolved_env) if resolved_env else None,
        )

    if transport == "http":
        return StreamableHTTPConnectionParams(
            url=endpoint,
            headers=dict(resolved_env) if resolved_env else None,
        )

    raise ValueError(f"unknown MCP transport: {transport!r}")
