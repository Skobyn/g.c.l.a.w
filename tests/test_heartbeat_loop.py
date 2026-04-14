"""Tests for the per-agent HeartbeatLoop background scheduler."""

from __future__ import annotations

import asyncio

import pytest
from unittest.mock import AsyncMock

from gclaw.heartbeat.config import HeartbeatConfig
from gclaw.heartbeat.reason import WakeReason
from gclaw.heartbeat.registry import HeartbeatRegistry
from gclaw.heartbeat.scheduler_loop import HeartbeatLoop


def _mk_service() -> AsyncMock:
    svc = AsyncMock()
    svc.run = AsyncMock(return_value={})
    return svc


@pytest.mark.asyncio
async def test_loop_fires_registered_agents():
    reg = HeartbeatRegistry()
    svc_a = _mk_service()
    svc_b = _mk_service()
    # Tiny intervals so both fire in-test.
    reg.register(
        "a", svc_a, HeartbeatConfig(enabled=True, every="50ms")
    )
    reg.register(
        "b", svc_b, HeartbeatConfig(enabled=True, every="50ms")
    )

    loop = HeartbeatLoop(reg, seed="test-seed", tick_interval_seconds=0.02)
    loop.start()
    try:
        # Give the loop enough wall-clock to cover the phase + at least
        # one fire per agent (phase is in [0, 50ms)).
        await asyncio.sleep(0.4)
    finally:
        await loop.stop()

    assert svc_a.run.await_count >= 1
    assert svc_b.run.await_count >= 1
    # Verify reason was INTERVAL
    for call in svc_a.run.await_args_list:
        assert call.kwargs.get("reason") == WakeReason.INTERVAL


@pytest.mark.asyncio
async def test_loop_skips_disabled_agents():
    reg = HeartbeatRegistry()
    svc = _mk_service()
    reg.register(
        "x", svc, HeartbeatConfig(enabled=False, every="10ms")
    )

    loop = HeartbeatLoop(reg, seed="s", tick_interval_seconds=0.01)
    loop.start()
    try:
        await asyncio.sleep(0.15)
    finally:
        await loop.stop()

    assert svc.run.await_count == 0


@pytest.mark.asyncio
async def test_loop_stop_is_clean():
    reg = HeartbeatRegistry()
    svc = _mk_service()
    reg.register(
        "x", svc, HeartbeatConfig(enabled=True, every="30m")
    )

    loop = HeartbeatLoop(reg, seed="s", tick_interval_seconds=0.02)
    loop.start()
    await asyncio.sleep(0.05)
    await loop.stop()
    # Second stop is a no-op.
    await loop.stop()
    assert loop._task is None


@pytest.mark.asyncio
async def test_loop_continues_after_service_exception():
    reg = HeartbeatRegistry()
    svc_a = AsyncMock()
    svc_a.run = AsyncMock(side_effect=RuntimeError("boom"))
    svc_b = _mk_service()
    reg.register("a", svc_a, HeartbeatConfig(enabled=True, every="50ms"))
    reg.register("b", svc_b, HeartbeatConfig(enabled=True, every="50ms"))

    loop = HeartbeatLoop(reg, seed="s", tick_interval_seconds=0.02)
    loop.start()
    try:
        await asyncio.sleep(0.4)
    finally:
        await loop.stop()

    # Both still got called despite a's raising.
    assert svc_a.run.await_count >= 1
    assert svc_b.run.await_count >= 1
