"""Board task models for the kanban project board."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing_extensions import Self

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    BACKLOG = "backlog"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    NEEDS_APPROVAL = "needs_approval"
    DONE = "done"
    FAILED = "failed"


# Valid forward transitions
_VALID_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.BACKLOG: {TaskStatus.QUEUED, TaskStatus.IN_PROGRESS},
    TaskStatus.QUEUED: {TaskStatus.IN_PROGRESS, TaskStatus.BACKLOG},
    TaskStatus.IN_PROGRESS: {
        TaskStatus.DONE,
        TaskStatus.FAILED,
        TaskStatus.NEEDS_APPROVAL,
    },
    TaskStatus.NEEDS_APPROVAL: {
        TaskStatus.IN_PROGRESS,
        TaskStatus.DONE,
        TaskStatus.FAILED,
    },
    TaskStatus.FAILED: {TaskStatus.QUEUED, TaskStatus.BACKLOG},
    TaskStatus.DONE: set(),
}


class TaskPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TaskSourceType(str, Enum):
    USER = "user"
    AGENT = "agent"
    CRON = "cron"


class CronMode(str, Enum):
    AUTO = "auto"
    TODO = "todo"


class TaskSource(BaseModel):
    type: TaskSourceType = TaskSourceType.USER
    origin: str | None = None


class CronConfig(BaseModel):
    schedule: str
    mode: CronMode = CronMode.TODO


class Attachment(BaseModel):
    type: str
    ref: str


class TaskResult(BaseModel):
    summary: str
    artifacts: list[str] = Field(default_factory=list)


class BoardTask(BaseModel):
    id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:12]}")
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.BACKLOG
    priority: TaskPriority = TaskPriority.MEDIUM
    source: TaskSource = Field(default_factory=TaskSource)
    assignee: str = ""
    dependencies: list[str] = Field(default_factory=list)
    attachments: list[Attachment] = Field(default_factory=list)
    requires_approval: bool = False
    cron: CronConfig | None = None
    result: TaskResult | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    approved_at: datetime | None = None
    approved_by: str | None = None
    approval_note: str | None = None
    rejected_at: datetime | None = None
    rejection_note: str | None = None

    def transition_to(self, new_status: TaskStatus) -> Self:
        valid = _VALID_TRANSITIONS.get(self.status, set())
        if new_status not in valid:
            raise ValueError(
                f"Cannot transition from {self.status} to {new_status}. "
                f"Valid targets: {valid}"
            )
        return self.model_copy(
            update={"status": new_status, "updated_at": datetime.now(timezone.utc)}
        )

    def complete(self, result: TaskResult) -> Self:
        moved = self.transition_to(TaskStatus.DONE)
        return moved.model_copy(update={"result": result})

    def to_firestore_dict(self) -> dict:
        d = self.model_dump(mode="json")
        d.pop("id")
        return d

    @classmethod
    def from_firestore_dict(cls, doc_id: str, data: dict) -> Self:
        return cls(id=doc_id, **data)
