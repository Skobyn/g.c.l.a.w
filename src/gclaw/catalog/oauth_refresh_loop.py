"""Background asyncio loop that refreshes tracked OAuth tokens."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gclaw.catalog.oauth_tokens import OAuthTokenManager

logger = logging.getLogger(__name__)


class OAuthRefreshLoop:
    """Periodically ticks ``OAuthTokenManager.ensure_fresh`` for every
    tracked SM path. Runs until ``stop()`` is called. Individual failures
    are logged and swallowed so a single bad secret never kills the loop.
    """

    def __init__(
        self,
        manager: "OAuthTokenManager",
        *,
        check_interval_seconds: int = 300,
    ) -> None:
        self._manager = manager
        self._interval = max(5, int(check_interval_seconds))
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(
            self._run(), name="oauth-refresh-loop"
        )
        logger.info(
            "oauth-refresh loop started (interval=%ss, tracked=%s)",
            self._interval,
            self._manager.tracked_paths(),
        )

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except asyncio.TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except (asyncio.CancelledError, Exception):
                    pass
        self._task = None

    async def tick_once(self) -> None:
        """Run one pass over all tracked paths. Exposed for tests."""
        for path in list(self._manager.tracked_paths()):
            try:
                await self._manager.ensure_fresh(path)
            except Exception:
                logger.exception(
                    "oauth-refresh tick failed for path=%s", path
                )

    async def _run(self) -> None:
        while not self._stop.is_set():
            await self.tick_once()
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=self._interval
                )
            except asyncio.TimeoutError:
                pass
