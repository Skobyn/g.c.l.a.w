"""In-process pubsub + ring buffer of recent heartbeat events."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from enum import Enum
from typing import Callable

from pydantic import BaseModel, Field

from gclaw.heartbeat.reason import WakeReason


class HeartbeatStatus(str, Enum):
    SENT = "sent"          # full reply delivered
    OK_TOKEN = "ok-token"  # reply was bare HEARTBEAT_OK (or short ack)
    OK_EMPTY = "ok-empty"  # nothing to do — skipped before agent call
    SKIPPED = "skipped"    # gated (active_hours, busy queue, etc)
    FAILED = "failed"


class HeartbeatEvent(BaseModel):
    agent_id: str
    status: HeartbeatStatus
    reason: WakeReason
    duration_ms: int = 0
    preview: str = ""  # first 100 chars of agent reply (if any)
    error: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class HeartbeatEventBus:
    """In-process pubsub + ring buffer of recent events."""

    def __init__(self, ring_size: int = 200) -> None:
        self._ring: deque[HeartbeatEvent] = deque(maxlen=ring_size)
        self._subscribers: list[Callable[[HeartbeatEvent], None]] = []

    def emit(self, event: HeartbeatEvent) -> None:
        self._ring.append(event)
        for sub in list(self._subscribers):
            try:
                sub(event)
            except Exception:
                # Never let a subscriber kill the bus.
                pass

    def subscribe(
        self, callback: Callable[[HeartbeatEvent], None]
    ) -> Callable[[], None]:
        self._subscribers.append(callback)

        def unsubscribe() -> None:
            try:
                self._subscribers.remove(callback)
            except ValueError:
                pass

        return unsubscribe

    def recent(
        self, limit: int = 50, agent_id: str | None = None
    ) -> list[HeartbeatEvent]:
        items = list(self._ring)
        if agent_id:
            items = [e for e in items if e.agent_id == agent_id]
        return items[-limit:][::-1]  # newest first


# Module-level singleton (acceptable for in-process).
_BUS = HeartbeatEventBus()


def get_event_bus() -> HeartbeatEventBus:
    return _BUS
