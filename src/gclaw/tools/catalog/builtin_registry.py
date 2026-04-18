"""Registry of builtin tool functions exposed to the catalog.

Modules in ``gclaw.tools.*`` decorate public callables with
``@tool_export`` to opt them into the catalog. The seeder walks the
registry at startup and upserts one ToolRecord per entry.

The registry is a process-level singleton — importing the module
populates it as side effect of decoration. ``clear_registry_for_tests``
is exposed purely for test isolation; production code must not call it.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class RegisteredTool:
    name: str
    description: str
    function: Callable[..., Any]
    function_path: str  # dotted import path — resolvable via importlib


_REGISTRY: dict[str, RegisteredTool] = {}


def _build_function_path(fn: Callable[..., Any]) -> str:
    module = getattr(fn, "__module__", "") or ""
    qualname = getattr(fn, "__qualname__", "") or getattr(fn, "__name__", "")
    # Nested functions show up with "<parent>.<locals>.<name>" — strip the
    # ``<locals>`` segment so importlib.getattr can still resolve.
    if ".<locals>." in qualname:
        qualname = qualname.rsplit(".<locals>.", 1)[-1]
    if not module:
        return qualname
    return f"{module}.{qualname}"


def _default_description(fn: Callable[..., Any]) -> str:
    doc = (inspect.getdoc(fn) or "").strip()
    if not doc:
        return ""
    return doc.splitlines()[0].strip()


def tool_export(
    *,
    name: str | None = None,
    description: str | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register a function as a catalog-visible builtin tool.

    ``name`` defaults to the function's ``__name__``; ``description``
    defaults to the first line of the docstring. Duplicate names
    raise ValueError at import time so drift is surfaced immediately
    instead of silently shadowing.
    """

    def _decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
        effective_name = name or fn.__name__
        effective_desc = description if description is not None else _default_description(fn)
        if effective_name in _REGISTRY:
            raise ValueError(
                f"tool_export: duplicate tool name {effective_name!r}"
            )
        _REGISTRY[effective_name] = RegisteredTool(
            name=effective_name,
            description=effective_desc,
            function=fn,
            function_path=_build_function_path(fn),
        )
        # Stash metadata on the function itself for downstream
        # introspection (matches the pattern the tester already uses).
        setattr(fn, "_tool_export_name", effective_name)
        setattr(fn, "_tool_export_description", effective_desc)
        return fn

    return _decorate


def get_registered() -> dict[str, RegisteredTool]:
    """Return a snapshot copy of the registry."""
    return dict(_REGISTRY)


def clear_registry_for_tests() -> None:
    """Wipe the registry. Tests only — never call from production code."""
    _REGISTRY.clear()
