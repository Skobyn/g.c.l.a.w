"""Per-run asyncio.Queue registry for the live dashboard fan-out.

The ``LiveSpanProcessor`` pushes OTel events into a per-run queue; the
SSE endpoint in :mod:`gclaw.api.dashboard_routes` drains that queue.
Bounded (default 1000 events); oldest event is dropped when full.

Single-process scope: each backend replica has its own registry. A
subscriber on replica A only sees events produced on replica A. Cloud
Run without session affinity will occasionally route the SSE subscribe
to a different replica than the runner — callers that need strict
live consistency across replicas should subscribe to the Firestore
``/users/{uid}/agent_runs/{run_id}`` doc instead, which is global.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class _RunChannel:
    queue: asyncio.Queue
    created_at: float = field(default_factory=time.monotonic)
    dropped: int = 0
    subscribers: int = 0


class RunRegistry:
    """Registry of per-``run_id`` event queues.

    Methods are safe to call from the asyncio event loop. ``put_nowait``
    is also safe to call from a plain-sync context such as an OTel span
    processor callback.
    """

    def __init__(self, *, max_queue_size: int = 1000) -> None:
        self._channels: dict[str, _RunChannel] = {}
        self._max_queue_size = max_queue_size

    def put_nowait(self, run_id: str, event: dict[str, Any]) -> None:
        """Push an event to the run's queue. Drops oldest when full."""
        if not run_id:
            return
        ch = self._channels.get(run_id)
        if ch is None:
            ch = _RunChannel(
                queue=asyncio.Queue(maxsize=self._max_queue_size)
            )
            self._channels[run_id] = ch
        try:
            ch.queue.put_nowait(event)
        except asyncio.QueueFull:
            try:
                ch.queue.get_nowait()
                ch.dropped += 1
                ch.queue.put_nowait(event)
            except asyncio.QueueEmpty:
                # Extremely unlikely race; don't block the producer.
                pass

    async def subscribe(self, run_id: str) -> asyncio.Queue:
        """Return the queue for ``run_id``, creating an empty one if needed."""
        ch = self._channels.get(run_id)
        if ch is None:
            ch = _RunChannel(
                queue=asyncio.Queue(maxsize=self._max_queue_size)
            )
            self._channels[run_id] = ch
        ch.subscribers += 1
        return ch.queue

    async def unsubscribe(self, run_id: str) -> None:
        ch = self._channels.get(run_id)
        if ch is None:
            return
        ch.subscribers = max(0, ch.subscribers - 1)
        if ch.subscribers == 0 and ch.queue.empty():
            # GC the channel so idle runs don't accumulate.
            self._channels.pop(run_id, None)

    def stats(self) -> dict[str, dict[str, int]]:
        return {
            run_id: {
                "queue": ch.queue.qsize(),
                "subscribers": ch.subscribers,
                "dropped": ch.dropped,
            }
            for run_id, ch in self._channels.items()
        }
