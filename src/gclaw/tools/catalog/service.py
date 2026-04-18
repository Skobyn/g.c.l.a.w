"""ToolCatalogService — CRUD orchestration over ToolRepo.

Thin layer mirroring ``catalog/service.py``. Accepts either a dict or
a typed config on create/update — dicts are validated through the
ToolConfig discriminator before being accepted, so clients never end
up with a partially-shaped record in Firestore.

Credential material stays in Secret Manager; the service only handles
the ``credential_ref`` path. Downstream kinds (MCP env-var injection,
HTTP auth, etc.) resolve the reference at tool-call time.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import TypeAdapter, ValidationError

from gclaw.tools.catalog.models import (
    ToolConfig,
    ToolKind,
    ToolRecord,
)

logger = logging.getLogger(__name__)


# Pre-built adapter for the discriminated-union — created once, reused
# across every create/update/validate call.
_TOOL_CONFIG_ADAPTER: TypeAdapter[Any] = TypeAdapter(ToolConfig)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ToolCatalogService:
    def __init__(self, tool_repo) -> None:
        self._repo = tool_repo

    # --- Create --------------------------------------------------------

    def create_tool(
        self,
        *,
        name: str,
        config: Any,
        enabled: bool = True,
        credential_ref: str | None = None,
    ) -> ToolRecord:
        coerced = self._coerce_config(config)
        record = ToolRecord(
            name=name,
            config=coerced,
            enabled=enabled,
            credential_ref=credential_ref,
        )
        return self._repo.create(record)

    # --- Read ----------------------------------------------------------

    def get_tool(self, tool_id: str) -> ToolRecord | None:
        return self._repo.get(tool_id)

    def list_tools(self) -> list[ToolRecord]:
        return self._repo.list_all()

    def list_enabled(self) -> list[ToolRecord]:
        return [t for t in self._repo.list_all() if t.enabled]

    def list_by_kind(self, kind: ToolKind) -> list[ToolRecord]:
        return [t for t in self._repo.list_all() if t.kind == kind]

    # --- Update --------------------------------------------------------

    def update_tool(self, tool_id: str, **updates: Any) -> ToolRecord:
        current = self._repo.get(tool_id)
        if current is None:
            raise ValueError(f"Tool {tool_id!r} not found")

        # Reserved fields callers cannot mutate.
        for field in ("id", "created_at", "kind"):
            updates.pop(field, None)

        payload = current.model_dump()
        if "config" in updates:
            updates["config"] = self._coerce_config(updates["config"]).model_dump()
        payload.update(updates)
        payload["updated_at"] = _now()
        new_record = ToolRecord(**payload)
        return self._repo.update(new_record)

    # --- Delete --------------------------------------------------------

    def delete_tool(self, tool_id: str) -> None:
        self._repo.delete(tool_id)

    # --- Validation helper --------------------------------------------

    def validate_config(self, config: Any) -> ToolConfig:
        """Parse a dict-or-typed config through the discriminated union.

        Raises pydantic.ValidationError on mismatch. Exposed so the
        admin API can surface the structured error before persisting.
        """
        return self._coerce_config(config)

    def _coerce_config(self, config: Any) -> Any:
        # Pass typed configs through unchanged.
        if not isinstance(config, dict):
            return config
        try:
            return _TOOL_CONFIG_ADAPTER.validate_python(config)
        except ValidationError:
            raise
