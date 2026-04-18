"""Unit tests for RunRegistry — per-run queue fan-out."""

from __future__ import annotations

import asyncio

import pytest

from gclaw.observability.run_registry import RunRegistry


@pytest.mark.asyncio
async def test_put_nowait_and_subscribe_roundtrip():
    reg = RunRegistry()
    reg.put_nowait("r1", {"event": "span.end", "data": {"n": 1}})
    reg.put_nowait("r1", {"event": "span.end", "data": {"n": 2}})

    q = await reg.subscribe("r1")
    assert q.qsize() == 2
    first = await asyncio.wait_for(q.get(), timeout=0.5)
    second = await asyncio.wait_for(q.get(), timeout=0.5)
    assert first["data"]["n"] == 1
    assert second["data"]["n"] == 2


@pytest.mark.asyncio
async def test_put_nowait_is_noop_for_empty_run_id():
    reg = RunRegistry()
    reg.put_nowait("", {"event": "x"})
    # Should not have created a channel for empty run_id.
    assert reg.stats() == {}


@pytest.mark.asyncio
async def test_queue_drops_oldest_when_full():
    reg = RunRegistry(max_queue_size=3)
    for i in range(5):
        reg.put_nowait("r1", {"n": i})
    stats = reg.stats()
    assert stats["r1"]["queue"] == 3
    # Two oldest (0, 1) were dropped to make room for (3, 4).
    assert stats["r1"]["dropped"] == 2
    q = await reg.subscribe("r1")
    values = [(await q.get())["n"] for _ in range(3)]
    assert values == [2, 3, 4]


@pytest.mark.asyncio
async def test_unsubscribe_gcs_idle_channels():
    reg = RunRegistry()
    q = await reg.subscribe("r1")
    assert "r1" in reg.stats()
    await reg.unsubscribe("r1")
    # Empty queue + no subscribers → channel is GC'd.
    assert "r1" not in reg.stats()
    # Sanity: the queue object is still usable post-GC.
    assert q.qsize() == 0
