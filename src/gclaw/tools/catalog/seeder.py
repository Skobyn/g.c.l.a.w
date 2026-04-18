"""Idempotent seeder that reflects the @tool_export registry into the catalog.

On boot: each registered function becomes a ToolRecord with a
BuiltinConfig pointing at the function's dotted path. Re-running is a
no-op for tools already present (matched by function_path) — user
edits (enable/disable, rename, etc.) are preserved.
"""

from __future__ import annotations

import logging
from typing import Any

from gclaw.tools.catalog.builtin_registry import RegisteredTool, get_registered
from gclaw.tools.catalog.models import BuiltinConfig, ToolKind

logger = logging.getLogger(__name__)


def seed_builtin_tools(
    service: Any, *, registry: dict[str, RegisteredTool] | None = None
) -> dict[str, int]:
    """Upsert one ToolRecord per entry in the registry.

    Returns a stats dict: ``{"created": N, "existing": M}``.

    Matching is keyed on ``BuiltinConfig.function_path`` — the name
    is allowed to drift (user can rename) but the dotted path
    uniquely identifies which registered function backs the record.
    """
    registry = registry if registry is not None else get_registered()
    existing_paths = {
        t.config.function_path
        for t in service.list_tools()
        if t.kind == ToolKind.BUILTIN
        and isinstance(t.config, BuiltinConfig)
    }
    created = 0
    existing = 0
    for entry in registry.values():
        if entry.function_path in existing_paths:
            existing += 1
            continue
        try:
            service.create_tool(
                name=entry.name,
                config=BuiltinConfig(function_path=entry.function_path),
            )
            created += 1
        except Exception:
            logger.warning(
                "tool_seeder: failed to create tool for %s",
                entry.function_path,
                exc_info=True,
            )
    if created or existing:
        logger.info(
            "tool_seeder: builtin reflection complete (created=%d, existing=%d)",
            created,
            existing,
        )
    return {"created": created, "existing": existing}
