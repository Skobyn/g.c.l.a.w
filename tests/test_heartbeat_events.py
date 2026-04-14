"""Tests for the in-process heartbeat event bus."""

from __future__ import annotations

from gclaw.heartbeat.events import (
    HeartbeatEvent,
    HeartbeatEventBus,
    HeartbeatStatus,
)
from gclaw.heartbeat.reason import WakeReason


def _make_event(agent_id: str = "orchestrator", preview: str = "hi") -> HeartbeatEvent:
    return HeartbeatEvent(
        agent_id=agent_id,
        status=HeartbeatStatus.SENT,
        reason=WakeReason.INTERVAL,
        duration_ms=5,
        preview=preview,
    )


def test_emit_then_recent_returns_event():
    bus = HeartbeatEventBus()
    ev = _make_event(preview="hello")
    bus.emit(ev)
    recent = bus.recent()
    assert len(recent) == 1
    assert recent[0].preview == "hello"


def test_subscribers_receive_events():
    bus = HeartbeatEventBus()
    received: list[HeartbeatEvent] = []
    unsub = bus.subscribe(lambda e: received.append(e))
    bus.emit(_make_event(preview="one"))
    bus.emit(_make_event(preview="two"))
    assert [e.preview for e in received] == ["one", "two"]

    unsub()
    bus.emit(_make_event(preview="three"))
    assert len(received) == 2  # no new after unsubscribe


def test_ring_eviction_at_maxlen():
    bus = HeartbeatEventBus(ring_size=3)
    for i in range(5):
        bus.emit(_make_event(preview=f"e{i}"))
    recent = bus.recent(limit=50)
    # newest-first, only last 3 retained
    assert [e.preview for e in recent] == ["e4", "e3", "e2"]


def test_agent_id_filter():
    bus = HeartbeatEventBus()
    bus.emit(_make_event(agent_id="a", preview="from-a"))
    bus.emit(_make_event(agent_id="b", preview="from-b"))
    bus.emit(_make_event(agent_id="a", preview="from-a-2"))
    only_a = bus.recent(agent_id="a")
    assert [e.preview for e in only_a] == ["from-a-2", "from-a"]


def test_failing_subscriber_does_not_break_bus():
    bus = HeartbeatEventBus()
    good: list[HeartbeatEvent] = []

    def bad(_e: HeartbeatEvent) -> None:
        raise RuntimeError("boom")

    bus.subscribe(bad)
    bus.subscribe(lambda e: good.append(e))

    # emit should not raise even though `bad` throws
    bus.emit(_make_event(preview="survived"))

    assert len(good) == 1
    assert good[0].preview == "survived"
    # and ring buffer still captured it
    assert len(bus.recent()) == 1
