"""Per-user event queue registry for cross-session delivery.

Parallels ``RunRegistry`` (per-session) but keyed on ``user_id`` so
events produced by a heartbeat run in one session can be delivered
to any chat session the user has open.

Used by ``BoardService._emit`` to fan task.* events to BOTH:
  - the current run's RunRegistry channel (for inline chat display)
  - the user's UserEventRegistry channel (for the background activity
    strip + any future cross-session notification surfaces)

Single-process scope — same caveat as RunRegistry. Cross-replica
delivery would require a pub/sub shim; for now SSE subscribers on a
different replica than the producer simply won't see those events
live, but Firestore snapshots of the board remain authoritative.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class _UserChannel:
    queue: asyncio.Queue
    created_at: float = field(default_factory=time.monotonic)
    dropped: int = 0
    subscribers: int = 0


class UserEventRegistry:
    """Registry of per-``user_id`` event queues.

    Mirrors RunRegistry shape. ``put_nowait`` is safe from sync
    contexts; ``subscribe`` / ``unsubscribe`` are asyncio-native.
    """

    def __init__(self, *, max_queue_size: int = 2000) -> None:
        self._channels: dict[str, _UserChannel] = {}
        self._max_queue_size = max_queue_size

    def put_nowait(self, user_id: str, event: dict[str, Any]) -> None:
        if not user_id:
            return
        ch = self._channels.get(user_id)
        if ch is None:
            ch = _UserChannel(
                queue=asyncio.Queue(maxsize=self._max_queue_size)
            )
            self._channels[user_id] = ch
        try:
            ch.queue.put_nowait(event)
        except asyncio.QueueFull:
            try:
                ch.queue.get_nowait()
                ch.dropped += 1
                ch.queue.put_nowait(event)
            except asyncio.QueueEmpty:
                pass

    async def subscribe(self, user_id: str) -> asyncio.Queue:
        ch = self._channels.get(user_id)
        if ch is None:
            ch = _UserChannel(
                queue=asyncio.Queue(maxsize=self._max_queue_size)
            )
            self._channels[user_id] = ch
        ch.subscribers += 1
        return ch.queue

    async def unsubscribe(self, user_id: str) -> None:
        ch = self._channels.get(user_id)
        if ch is None:
            return
        ch.subscribers = max(0, ch.subscribers - 1)
        if ch.subscribers == 0 and ch.queue.empty():
            self._channels.pop(user_id, None)

    def stats(self) -> dict[str, dict[str, int]]:
        return {
            uid: {
                "queue": ch.queue.qsize(),
                "subscribers": ch.subscribers,
                "dropped": ch.dropped,
            }
            for uid, ch in self._channels.items()
        }
