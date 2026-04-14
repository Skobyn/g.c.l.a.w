"""Cron model for scheduled task definitions.

Schema v2 — schedule, payload, and delivery are tagged unions.
Backwards-compatible with the old flat `{title, schedule: str, mode, ...}` shape
via ``Cron.from_firestore_dict``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field
from typing_extensions import Self


class CronMode(str, Enum):
    """Mode controlling how an agent_turn payload materializes on the board."""

    AUTO = "auto"
    TODO = "todo"


class CronStatus(str, Enum):
    """Legacy status flag — kept for backward compat. Prefer ``enabled`` bool."""

    ACTIVE = "active"
    PAUSED = "paused"


# --- Schedule union ---------------------------------------------------------


class AtSchedule(BaseModel):
    kind: Literal["at"] = "at"
    at: datetime


class EverySchedule(BaseModel):
    kind: Literal["every"] = "every"
    every_ms: int
    anchor_ms: int | None = None


class CronExprSchedule(BaseModel):
    kind: Literal["cron"] = "cron"
    expr: str
    tz: str | None = None
    stagger_ms: int | None = None


Schedule = Annotated[
    Union[AtSchedule, EverySchedule, CronExprSchedule],
    Field(discriminator="kind"),
]


# --- Payload union ----------------------------------------------------------


class SystemEventPayload(BaseModel):
    kind: Literal["system_event"] = "system_event"
    text: str


class AgentTurnPayload(BaseModel):
    kind: Literal["agent_turn"] = "agent_turn"
    message: str
    model: str | None = None
    timeout_seconds: int | None = None
    light_context: bool = False


Payload = Annotated[
    Union[SystemEventPayload, AgentTurnPayload],
    Field(discriminator="kind"),
]


# --- Delivery union ---------------------------------------------------------


class DeliveryNone(BaseModel):
    mode: Literal["none"] = "none"


class DeliveryAnnounce(BaseModel):
    mode: Literal["announce"] = "announce"
    # Transport registry key; "default" means use the system default
    # transport configured via CRON_ANNOUNCE_BACKEND.
    transport: str = "default"
    channel: str | None = None
    to: str | None = None
    account_id: str | None = None
    best_effort: bool = False


class DeliveryWebhook(BaseModel):
    mode: Literal["webhook"] = "webhook"
    url: str
    best_effort: bool = False


Delivery = Annotated[
    Union[DeliveryNone, DeliveryAnnounce, DeliveryWebhook],
    Field(discriminator="mode"),
]


# --- Failure alert ----------------------------------------------------------


class FailureAlert(BaseModel):
    after: int = 3
    cooldown_ms: int = 3_600_000
    channel: str | None = None
    to: str | None = None
    url: str | None = None
    mode: Literal["announce", "webhook"] = "announce"
    # Transport registry key for announce-mode alerts; "default" means
    # use the system default transport.
    transport: str = "default"


# --- Cron -------------------------------------------------------------------


class Cron(BaseModel):
    """A cron job definition stored in Firestore.

    When triggered:
    - payload.kind == "agent_turn" + mode="auto": task queued for dispatch
    - payload.kind == "agent_turn" + mode="todo": task lands in backlog
    - payload.kind == "system_event": text enqueued for next heartbeat
    """

    id: str = Field(default_factory=lambda: f"cron_{uuid.uuid4().hex[:12]}")
    title: str
    description: str = ""

    schedule: Schedule
    payload: Payload
    delivery: Delivery = Field(default_factory=DeliveryNone)
    failure_alert: FailureAlert | None = None

    mode: CronMode = CronMode.TODO
    assignee: str
    task_priority: str = "medium"

    wake_mode: Literal["now", "next-heartbeat"] = "now"
    enabled: bool = True
    delete_after_run: bool = False

    # Legacy status — mirrors ``enabled`` for back-compat with code that
    # still reads CronStatus.ACTIVE/PAUSED. Source of truth is ``enabled``.
    status: CronStatus = CronStatus.ACTIVE

    consecutive_errors: int = 0
    last_error: str | None = None
    last_alert_at: datetime | None = None

    last_run: datetime | None = None
    next_run: datetime | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def model_post_init(self, __context) -> None:
        # Keep ``status`` and ``enabled`` in sync without mutating explicit
        # caller intent: if caller set status=PAUSED, reflect in enabled; if
        # caller set enabled=False, reflect in status.
        if self.status == CronStatus.PAUSED and self.enabled:
            object.__setattr__(self, "enabled", False)
        elif not self.enabled and self.status == CronStatus.ACTIVE:
            object.__setattr__(self, "status", CronStatus.PAUSED)

    def record_run(self) -> Self:
        """Return a copy with last_run set to now and errors reset."""
        now = datetime.now(timezone.utc)
        return self.model_copy(
            update={
                "last_run": now,
                "updated_at": now,
                "consecutive_errors": 0,
                "last_error": None,
            }
        )

    def record_failure(self, error: str) -> Self:
        now = datetime.now(timezone.utc)
        return self.model_copy(
            update={
                "updated_at": now,
                "consecutive_errors": self.consecutive_errors + 1,
                "last_error": error,
            }
        )

    def to_firestore_dict(self) -> dict:
        d = self.model_dump(mode="json")
        d.pop("id")
        return d

    @classmethod
    def from_firestore_dict(cls, doc_id: str, data: dict) -> Self:
        data = dict(data)  # don't mutate caller's dict

        # --- Back-compat migration ---------------------------------------
        # Old shape: schedule is a plain cron string and there's no payload.
        if isinstance(data.get("schedule"), str) and "payload" not in data:
            old_expr: str = data["schedule"]
            data["schedule"] = {"kind": "cron", "expr": old_expr}

            old_mode = data.get("mode", CronMode.TODO.value)
            message = data.get("title") or data.get("description") or ""
            if old_mode == CronMode.AUTO.value:
                data["payload"] = {"kind": "agent_turn", "message": message}
            else:
                # For TODO-mode legacy crons the board task is still the
                # desired outcome — keep them as agent_turn so execute()
                # behaviour is unchanged. system_event would change semantics.
                data["payload"] = {"kind": "agent_turn", "message": message}

            data.setdefault("delivery", {"mode": "none"})
            data.setdefault("wake_mode", "now")

        return cls(id=doc_id, **data)
