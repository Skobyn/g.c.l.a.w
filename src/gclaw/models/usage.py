"""Data model for unified usage telemetry events.

Four event kinds — model calls, agent invocations, skill uses, tool calls —
share a single shape so they can be aggregated in a uniform admin dashboard.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class UsageKind(str, Enum):
    MODEL = "model"
    AGENT = "agent"
    SKILL = "skill"
    TOOL = "tool"


class UsageEvent(BaseModel):
    """One telemetry record. Kind-specific fields are optional."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: f"use_{uuid.uuid4().hex[:12]}")
    kind: UsageKind
    name: str  # model_id | agent_name | skill_name | tool_name
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    user_id: str | None = None
    session_id: str | None = None
    duration_ms: int = 0
    success: bool = True
    error: str | None = None

    # model-specific
    provider_id: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None

    # agent / skill / tool
    caller: str | None = None
    metadata: dict = Field(default_factory=dict)

    def to_firestore_dict(self) -> dict:
        """Serialize for Firestore.

        Uses ``mode="python"`` so datetime stays as a native
        ``datetime`` and Firestore persists it as a Timestamp. The old
        ``mode="json"`` path wrote timestamps as ISO-8601 *strings*,
        which made ``where("timestamp", ">=", <datetime>)`` silently
        return zero rows — the type mismatch between the stored string
        and the queried Timestamp produced no matches. That's why the
        admin usage summary / timeseries / top-N all returned zero
        while the no-filter events endpoint worked.
        """
        d = self.model_dump(mode="python")
        d.pop("id", None)
        return d

    @classmethod
    def from_firestore_dict(cls, doc_id: str, data: dict) -> "UsageEvent":
        data = dict(data)
        return cls(id=doc_id, **data)
