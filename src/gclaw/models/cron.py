"""Cron model for scheduled task definitions."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field
from typing_extensions import Self


class CronMode(str, Enum):
    AUTO = "auto"
    TODO = "todo"


class CronStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"


class Cron(BaseModel):
    """A cron job definition stored in Firestore.

    When triggered:
    - mode="auto": creates a task on the board and immediately dispatches it
    - mode="todo": creates a task in backlog for manual prioritization
    """

    id: str = Field(default_factory=lambda: f"cron_{uuid.uuid4().hex[:12]}")
    title: str
    description: str = ""
    schedule: str  # cron expression, e.g. "0 8 * * *"
    mode: CronMode = CronMode.TODO
    status: CronStatus = CronStatus.ACTIVE
    assignee: str  # which agent handles the created task
    task_priority: str = "medium"  # priority for created tasks
    last_run: datetime | None = None
    next_run: datetime | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def record_run(self) -> Self:
        """Return a copy with last_run set to now."""
        now = datetime.now(timezone.utc)
        return self.model_copy(
            update={"last_run": now, "updated_at": now}
        )

    def to_firestore_dict(self) -> dict:
        d = self.model_dump(mode="json")
        d.pop("id")
        return d

    @classmethod
    def from_firestore_dict(cls, doc_id: str, data: dict) -> Self:
        return cls(id=doc_id, **data)
