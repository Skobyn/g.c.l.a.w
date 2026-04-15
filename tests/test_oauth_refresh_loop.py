"""Tests for OAuthRefreshLoop."""

from __future__ import annotations

import asyncio

import pytest

from gclaw.catalog.oauth_refresh_loop import OAuthRefreshLoop


class FakeManager:
    def __init__(self, paths: list[str], fail_paths: set[str] | None = None):
        self._paths = list(paths)
        self.calls: list[str] = []
        self._fail_paths = fail_paths or set()

    def tracked_paths(self) -> list[str]:
        return list(self._paths)

    async def ensure_fresh(self, path: str) -> None:
        self.calls.append(path)
        if path in self._fail_paths:
            raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_tick_fires_ensure_fresh_on_each_path():
    mgr = FakeManager(["p1", "p2", "p3"])
    loop = OAuthRefreshLoop(mgr, check_interval_seconds=60)
    await loop.tick_once()
    assert mgr.calls == ["p1", "p2", "p3"]


@pytest.mark.asyncio
async def test_tick_swallows_individual_failures():
    mgr = FakeManager(["good", "bad", "also-good"], fail_paths={"bad"})
    loop = OAuthRefreshLoop(mgr, check_interval_seconds=60)
    # Must not raise even though "bad" throws.
    await loop.tick_once()
    assert mgr.calls == ["good", "bad", "also-good"]


@pytest.mark.asyncio
async def test_start_stop_runs_loop():
    mgr = FakeManager(["a"])
    loop = OAuthRefreshLoop(mgr, check_interval_seconds=1)
    loop.start()
    # Give it one iteration to fire.
    await asyncio.sleep(0.1)
    await loop.stop()
    assert "a" in mgr.calls
