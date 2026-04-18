"""In-memory fake ToolRepo used by the tool-catalog service tests."""

from __future__ import annotations

from gclaw.tools.catalog.models import ToolRecord


class FakeToolRepo:
    def __init__(self) -> None:
        self.store: dict[str, ToolRecord] = {}

    def create(self, t: ToolRecord) -> ToolRecord:
        self.store[t.id] = t
        return t

    def get(self, tool_id: str) -> ToolRecord | None:
        return self.store.get(tool_id)

    def update(self, t: ToolRecord) -> ToolRecord:
        self.store[t.id] = t
        return t

    def delete(self, tool_id: str) -> None:
        self.store.pop(tool_id, None)

    def list_all(self) -> list[ToolRecord]:
        return list(self.store.values())
