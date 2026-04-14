"""Background asyncio loop that drives per-agent heartbeats by phase.

Each registered agent has a deterministic phase offset within its
interval window (see :mod:`gclaw.heartbeat.schedule`), so two agents on
the same cadence won't thunder-herd. The loop wakes on a short tick
(default 5s), checks which agents are due, and dispatches them.

A single shared loop is cheap; per-agent ``HeartbeatService.run`` does
the heavy work. Ticks run sequentially to preserve Firestore write
ordering and avoid flooding the agent runtime.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from gclaw.heartbeat.config import parse_duration_ms
from gclaw.heartbeat.reason import WakeReason
from gclaw.heartbeat.schedule import compute_next_due_ms, resolve_phase_ms

if TYPE_CHECKING:
    from gclaw.heartbeat.registry import HeartbeatRegistry

logger = logging.getLogger(__name__)


class HeartbeatLoop:
    """Background asyncio loop that ticks per-agent heartbeats by phase."""

    def __init__(
        self,
        registry: "HeartbeatRegistry",
        seed: str,
        *,
        tick_interval_seconds: float = 5.0,
    ) -> None:
        self._registry = registry
        self._seed = seed
        self._tick = tick_interval_seconds
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        # next-due ms per agent
        self._next_due: dict[str, int] = {}

    def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="heartbeat-loop")
        logger.info(
            "Heartbeat loop started (agents=%s)",
            self._registry.all_agents(),
        )

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except asyncio.TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except (asyncio.CancelledError, Exception):
                    pass
        self._task = None

    async def _run(self) -> None:
        while not self._stop.is_set():
            now_ms = int(time.time() * 1000)
            for agent_name, service, cfg in self._registry.items():
                if not cfg.enabled:
                    continue
                try:
                    interval_ms = parse_duration_ms(cfg.every)
                except ValueError:
                    logger.warning(
                        "heartbeat: bad 'every' on agent=%s: %r",
                        agent_name,
                        cfg.every,
                    )
                    continue
                if interval_ms <= 0:
                    continue

                if agent_name not in self._next_due:
                    phase = resolve_phase_ms(
                        agent_name, interval_ms, self._seed
                    )
                    self._next_due[agent_name] = compute_next_due_ms(
                        now_ms, interval_ms, phase
                    )

                if now_ms >= self._next_due[agent_name]:
                    try:
                        await service.run(reason=WakeReason.INTERVAL)
                    except Exception:
                        logger.exception(
                            "heartbeat tick failed agent=%s", agent_name
                        )
                    phase = resolve_phase_ms(
                        agent_name, interval_ms, self._seed
                    )
                    self._next_due[agent_name] = compute_next_due_ms(
                        now_ms + 1, interval_ms, phase
                    )

            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._tick)
            except asyncio.TimeoutError:
                pass
