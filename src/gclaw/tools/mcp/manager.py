"""Connection cache + probe runner for MCP-kind tools.

One ``McpClientManager`` lives in the app's composition root and is
shared by both:
  - the AgentFactory (via ToolBindingService) — it hands back a cached
    ADK ``McpToolset`` per catalog record so repeat agent builds
    don't reconnect;
  - the /admin/tools/{id}/test endpoint — it probes via ``get_tools``
    and returns the server's advertised tool names.

Credential resolution is delegated via the ``secret_resolver``
callable injected at construction; this keeps the manager free of any
google-cloud-secretmanager import and trivially mockable in tests.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)


_PROBE_TIMEOUT_SECONDS = 10.0


# Module-level ADK import so unittest.mock.patch() can rebind it from
# tests without poking into every construction call-site. Wrapped in
# try/except so environments without the optional google-adk MCP
# extras still import this module — attempts to actually build a
# toolset will fail loudly when the sentinel is None.
try:
    from google.adk.tools.mcp_tool import McpToolset  # type: ignore
except Exception:  # pragma: no cover — lazy import surface
    McpToolset = None  # type: ignore[assignment]


class McpClientManager:
    def __init__(
        self,
        *,
        secret_resolver: Callable[[str], str | None] | None = None,
    ) -> None:
        self._cache: dict[str, Any] = {}
        self._resolver = secret_resolver or (lambda _ref: None)

    def get_toolset(self, record: Any) -> Any:
        """Return a cached ``McpToolset`` for ``record`` — build if absent.

        Cache key is the record's ``id``. Changing the config on an
        existing record means the admin UI (Phase 7) should call
        ``invalidate(record.id)`` so the next binding rebuilds; that
        hook lives here but isn't wired yet.
        """
        cached = self._cache.get(record.id)
        if cached is not None:
            return cached

        toolset = self._build_toolset(record)
        self._cache[record.id] = toolset
        return toolset

    def invalidate(self, tool_id: str) -> None:
        """Drop a cached toolset (called by admin updates/deletes)."""
        toolset = self._cache.pop(tool_id, None)
        if toolset is None:
            return
        close = getattr(toolset, "close", None)
        if close is None:
            return
        # Fire-and-forget: we don't care about close completion here,
        # just that we stop referencing it.
        try:
            result = close()
            if asyncio.iscoroutine(result):
                # Schedule the close on the running loop if any; else
                # swallow — invalidate is a sync entry point.
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(result)
                except RuntimeError:
                    asyncio.run(result)
        except Exception:
            logger.warning(
                "mcp-manager: close during invalidate failed for %s",
                tool_id,
                exc_info=True,
            )

    async def close_all(self) -> None:
        """Close every cached toolset and drop the cache."""
        items = list(self._cache.items())
        self._cache.clear()
        for tool_id, toolset in items:
            close = getattr(toolset, "close", None)
            if close is None:
                continue
            try:
                await close()
            except Exception:
                logger.warning(
                    "mcp-manager: close during close_all failed for %s",
                    tool_id,
                    exc_info=True,
                )

    async def probe(self, record: Any) -> dict:
        """Connect, list tools, close. Returns {ok, latency_ms, tools?, error?}.

        Uses an ephemeral toolset (not the cached one) so a probe
        click doesn't evict an active agent's connection.
        """
        start = time.perf_counter()
        toolset = self._build_toolset(record)
        try:
            tools = await asyncio.wait_for(
                toolset.get_tools(), timeout=_PROBE_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            latency = (time.perf_counter() - start) * 1000
            await _safe_close(toolset)
            return {
                "ok": False,
                "latency_ms": round(latency, 2),
                "error": f"timed out after {_PROBE_TIMEOUT_SECONDS:.0f}s",
            }
        except Exception as e:  # noqa: BLE001
            latency = (time.perf_counter() - start) * 1000
            await _safe_close(toolset)
            return {
                "ok": False,
                "latency_ms": round(latency, 2),
                "error": str(e),
            }

        await _safe_close(toolset)
        latency = (time.perf_counter() - start) * 1000
        names = [getattr(t, "name", "<unnamed>") for t in tools]
        return {
            "ok": True,
            "latency_ms": round(latency, 2),
            "tools": names[:50],
        }

    # --- internals ------------------------------------------------------

    def _build_toolset(self, record: Any) -> Any:
        from gclaw.tools.mcp.client import (
            build_connection_params,
            resolve_env_with_credential,
        )

        if McpToolset is None:
            raise RuntimeError(
                "google-adk MCP extras not installed — McpToolset unavailable"
            )

        credential_value = None
        ref = getattr(record, "credential_ref", None)
        if ref:
            try:
                credential_value = self._resolver(ref)
            except Exception:
                logger.warning(
                    "mcp-manager: secret resolver raised for %s",
                    ref,
                    exc_info=True,
                )

        env = dict(getattr(record.config, "env", None) or {})
        resolved_env = resolve_env_with_credential(env, credential_value)

        params = build_connection_params(
            record.config, resolved_env=resolved_env
        )
        allowed = getattr(record.config, "allowed_tools", None)
        return McpToolset(
            connection_params=params,
            tool_filter=allowed,
        )


async def _safe_close(toolset: Any) -> None:
    close = getattr(toolset, "close", None)
    if close is None:
        return
    try:
        await close()
    except Exception:
        logger.debug("mcp-manager: close failed", exc_info=True)
