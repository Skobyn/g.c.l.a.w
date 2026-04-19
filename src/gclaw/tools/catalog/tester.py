"""Per-kind probe dispatch for the Tool Catalog test endpoint.

Every probe returns the same shape as the model-catalog test connection
(ok/latency_ms/error/sample_response) so the admin UI can render a
uniform success/failure banner. Probes never raise — exceptions are
caught and surfaced via ``error``.

Phase 2 ships the dispatch + the builtin probe. MCP / HTTP / Code-exec
probes return a stub "not yet wired" response until Phases 4, 5, 6 land;
those phases will overwrite the corresponding branch rather than touch
this module's structure.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import time
from typing import Any

from gclaw.tools.catalog.models import ToolKind, ToolRecord

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 10.0


# Module-level injection points for per-kind dependencies that live
# elsewhere in the composition graph. ``main.py`` wires them up once
# at startup; tests set/reset them via the exported setters. When a
# dependency is None the corresponding branch returns its Phase-2
# stub response so the dispatch shape stays stable.
_mcp_manager: Any = None


def set_mcp_manager(manager: Any) -> None:
    """Install (or clear) the shared McpClientManager used for probes."""
    global _mcp_manager
    _mcp_manager = manager


def _result(
    ok: bool,
    *,
    latency_ms: float,
    error: str | None = None,
    sample_response: Any = None,
) -> dict:
    return {
        "ok": ok,
        "latency_ms": round(latency_ms, 2),
        "error": error,
        "sample_response": sample_response,
    }


async def probe_tool(record: ToolRecord) -> dict:
    """Dispatch on kind; return a uniform probe-result dict.

    Named ``probe_tool`` (not ``test_tool``) so pytest doesn't try to
    discover it as a test function. Never raises — every exception is
    caught and reported via the ``error`` field.
    """
    start = time.perf_counter()
    try:
        if record.kind == ToolKind.BUILTIN:
            return await _probe_builtin(record, start)
        if record.kind == ToolKind.MCP:
            return await _probe_mcp(record, start)
        if record.kind == ToolKind.HTTP_API:
            return _not_yet(start, "HTTP-API probe will be wired in Phase 5")
        if record.kind == ToolKind.CODE_EXEC:
            return _not_yet(start, "Code-exec probe will be wired in Phase 6")
    except Exception as e:  # noqa: BLE001 — user-facing summary
        latency = (time.perf_counter() - start) * 1000
        return _result(False, latency_ms=latency, error=str(e))

    latency = (time.perf_counter() - start) * 1000
    return _result(
        False,
        latency_ms=latency,
        error=f"Unsupported tool kind: {record.kind}",
    )


def _not_yet(start: float, message: str) -> dict:
    latency = (time.perf_counter() - start) * 1000
    return _result(False, latency_ms=latency, error=message)


async def _probe_mcp(record: ToolRecord, start: float) -> dict:
    if _mcp_manager is None:
        return _not_yet(start, "MCP probe: manager not wired (Phase 4 dep missing)")
    outcome = await _mcp_manager.probe(record)
    latency = outcome.get("latency_ms")
    if latency is None:
        latency = (time.perf_counter() - start) * 1000
    if outcome.get("ok"):
        return _result(
            True,
            latency_ms=latency,
            sample_response={"tools": outcome.get("tools", [])},
        )
    return _result(
        False,
        latency_ms=latency,
        error=outcome.get("error") or "unknown MCP probe error",
    )


async def _probe_builtin(record: ToolRecord, start: float) -> dict:
    """Verify the dotted path resolves to a callable and report the signature."""
    function_path = getattr(record.config, "function_path", "")
    if not function_path or "." not in function_path:
        latency = (time.perf_counter() - start) * 1000
        return _result(
            False,
            latency_ms=latency,
            error=f"function_path must be a dotted import path, got: {function_path!r}",
        )

    module_path, _, attr_name = function_path.rpartition(".")
    try:
        module = importlib.import_module(module_path)
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return _result(
            False,
            latency_ms=latency,
            error=f"could not import {module_path!r}: {e}",
        )

    fn = getattr(module, attr_name, None)
    if fn is None or not callable(fn):
        latency = (time.perf_counter() - start) * 1000
        return _result(
            False,
            latency_ms=latency,
            error=f"{function_path!r} resolved to {fn!r} (not a callable)",
        )

    # Capture the signature without invoking the function — builtins
    # with required args would fail a no-op call, which says nothing
    # about whether the binding works.
    try:
        sig = str(inspect.signature(fn))
    except (TypeError, ValueError):
        sig = "(unknown signature)"
    doc = (inspect.getdoc(fn) or "").strip().splitlines()
    summary = doc[0] if doc else ""

    latency = (time.perf_counter() - start) * 1000
    return _result(
        True,
        latency_ms=latency,
        sample_response={
            "function_path": function_path,
            "signature": sig,
            "summary": summary,
        },
    )
