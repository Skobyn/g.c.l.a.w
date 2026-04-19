"""ToolBindingService — resolve catalog IDs to ADK-ready tool callables.

Takes an agent's ``catalog_tool_ids`` list from its ``AgentOverride``
and returns the corresponding python callables. Failures (disabled
tool, broken function_path, missing record) are silent skips with a
logged warning — a catalog misconfiguration must never take an agent
down.

Phase 3 handles the BUILTIN kind only. MCP / HTTP_API / CODE_EXEC
records are recognized and skipped; Phases 4–6 fill in the matching
branches in this module.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, Callable

from gclaw.tools.catalog.models import (
    BuiltinConfig,
    ToolKind,
)

logger = logging.getLogger(__name__)


class ToolBindingService:
    def __init__(
        self,
        *,
        catalog_service: Any,
        mcp_manager: Any | None = None,
        secret_resolver: Any | None = None,
        http_transport: Any | None = None,
        code_exec_runner: Any | None = None,
    ) -> None:
        self._catalog = catalog_service
        # Optional MCP manager (Phase 4). When absent, MCP-kind records
        # are silently skipped — binding stays safe without the
        # additional dependency.
        self._mcp_manager = mcp_manager
        # Phase 5 deps: callable that takes an SM resource path and
        # returns the value, and an optional httpx transport used by
        # tests. When the resolver is absent, HTTP-API tools bind but
        # skip auth — useful for NoAuth configurations.
        self._secret_resolver = secret_resolver
        self._http_transport = http_transport
        # Phase 6: code-exec runner (LocalRunner or RemoteRunner).
        # None disables the kind entirely — records still list but
        # bind to nothing, matching the pre-Phase-6 stub behavior.
        self._code_exec_runner = code_exec_runner

    def resolve_catalog_tools(
        self, tool_ids: list[str] | None
    ) -> list[Any]:
        """Return the list of callables / toolsets for the given IDs.

        Order is preserved. Invalid / disabled entries are dropped
        with a debug log line, not raised. An HTTP_API record
        materializes into MULTIPLE callables (one per allowed
        operation), which are flattened into the result list.
        """
        if not tool_ids:
            return []
        out: list[Any] = []
        for tid in tool_ids:
            record = self._catalog.get_tool(tid)
            if record is None:
                logger.debug(
                    "tool_binding: catalog tool %s not found (user override references a missing record)",
                    tid,
                )
                continue
            if not record.enabled:
                logger.debug(
                    "tool_binding: catalog tool %s is disabled; skipping",
                    tid,
                )
                continue
            resolved = self._resolve_one(record)
            if resolved is None:
                continue
            if isinstance(resolved, list):
                out.extend(resolved)
            else:
                out.append(resolved)
        return out

    def _resolve_one(self, record: Any) -> Any | None:
        kind = record.kind
        if kind == ToolKind.BUILTIN and isinstance(record.config, BuiltinConfig):
            return self._resolve_builtin(record.config.function_path)
        if kind == ToolKind.MCP:
            if self._mcp_manager is None:
                logger.debug(
                    "tool_binding: MCP manager not wired; skipping %s",
                    record.id,
                )
                return None
            try:
                return self._mcp_manager.get_toolset(record)
            except Exception:
                logger.warning(
                    "tool_binding: failed to build MCP toolset for %s",
                    record.id,
                    exc_info=True,
                )
                return None
        if kind == ToolKind.HTTP_API:
            return self._resolve_http_api(record)
        if kind == ToolKind.CODE_EXEC:
            if self._code_exec_runner is None:
                logger.debug(
                    "tool_binding: code_exec runner not wired; skipping %s",
                    record.id,
                )
                return None
            return _build_code_exec_callable(
                record=record, runner=self._code_exec_runner
            )
        logger.warning(
            "tool_binding: unknown tool kind %r on %s; skipping",
            kind,
            record.id,
        )
        return None

    def _resolve_http_api(self, record: Any) -> list[Callable[..., Any]] | None:
        try:
            from gclaw.tools.openapi_mcp import build_tool, load_spec
        except Exception:
            logger.warning(
                "tool_binding: openapi_mcp unavailable; skipping %s",
                record.id,
                exc_info=True,
            )
            return None
        try:
            ops = load_spec(record.config, http_transport=self._http_transport)
        except Exception:
            logger.warning(
                "tool_binding: OpenAPI spec load failed for %s",
                record.id,
                exc_info=True,
            )
            return None
        resolver = self._secret_resolver or (lambda _ref: None)
        out: list[Callable[..., Any]] = []
        for op in ops:
            try:
                out.append(
                    build_tool(
                        op,
                        auth=record.config.auth,
                        base_url=record.config.base_url,
                        secret_resolver=resolver,
                        http_transport=self._http_transport,
                    )
                )
            except Exception:
                logger.warning(
                    "tool_binding: build_tool failed for op %s",
                    op.operation_id,
                    exc_info=True,
                )
        return out or None

    @staticmethod
    def _resolve_builtin(function_path: str) -> Callable[..., Any] | None:
        if not function_path or "." not in function_path:
            logger.warning(
                "tool_binding: invalid function_path %r; skipping",
                function_path,
            )
            return None
        module_path, _, attr = function_path.rpartition(".")
        try:
            module = importlib.import_module(module_path)
        except Exception:
            logger.warning(
                "tool_binding: could not import %r",
                module_path,
                exc_info=True,
            )
            return None
        fn = getattr(module, attr, None)
        if fn is None or not callable(fn):
            logger.warning(
                "tool_binding: %s resolved to %r (not callable)",
                function_path,
                fn,
            )
            return None
        return fn


def _build_code_exec_callable(*, record: Any, runner: Any) -> Callable[..., Any]:
    """Wrap a code-exec runner into a single ADK-ready tool callable.

    The callable takes a ``code`` kwarg and routes to the runner's
    ``execute`` method, stamping the record's CodeExecConfig onto
    every call. The returned structured dict is rendered to a
    compact text summary the LLM can reason about.
    """
    config = record.config
    name = record.name or f"code_exec_{record.id}"

    async def _call(code: str) -> str:
        try:
            out = await runner.execute(code=code, config=config)
        except Exception as e:
            return f"code-exec error: {e}"
        return _render_code_exec_result(out)

    _call.__name__ = name.replace("-", "_").replace(" ", "_")
    _call.__doc__ = (
        f"Execute {config.runtime} code in a sandboxed runner "
        f"(timeout={config.timeout_seconds}s, memory={config.memory_mb}MB, "
        f"network={config.network})."
    )
    return _call


def _render_code_exec_result(out: dict) -> str:
    parts = [f"exit_code={out.get('exit_code', -1)}"]
    parts.append(f"duration_ms={out.get('duration_ms', 0)}")
    if out.get("error"):
        parts.append(f"error={out['error']}")
    stdout = out.get("stdout") or ""
    stderr = out.get("stderr") or ""
    head = " ".join(parts)
    sections = [head]
    if stdout:
        sections.append(f"STDOUT:\n{stdout}")
    if stderr:
        sections.append(f"STDERR:\n{stderr}")
    if out.get("truncated"):
        sections.append("(output truncated)")
    return "\n".join(sections)
