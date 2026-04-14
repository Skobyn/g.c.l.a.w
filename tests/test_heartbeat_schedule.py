"""Tests for the phase-staggered heartbeat scheduler helpers."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from gclaw.heartbeat.config import ActiveHours
from gclaw.heartbeat.schedule import (
    compute_next_due_ms,
    is_within_active_hours,
    resolve_phase_ms,
)


def test_resolve_phase_is_deterministic():
    a = resolve_phase_ms("orchestrator", 60_000, "seed-1")
    b = resolve_phase_ms("orchestrator", 60_000, "seed-1")
    assert a == b
    assert 0 <= a < 60_000


def test_resolve_phase_differs_across_agents():
    a = resolve_phase_ms("alpha", 60_000, "seed-1")
    b = resolve_phase_ms("beta", 60_000, "seed-1")
    c = resolve_phase_ms("gamma", 60_000, "seed-1")
    # Different agent ids should almost never collide; assert at least two
    # distinct phases out of three.
    assert len({a, b, c}) >= 2


def test_resolve_phase_differs_across_seeds():
    a = resolve_phase_ms("orchestrator", 60_000, "seed-1")
    b = resolve_phase_ms("orchestrator", 60_000, "seed-2")
    assert a != b


def test_resolve_phase_zero_interval():
    assert resolve_phase_ms("x", 0, "s") == 0


def test_compute_next_due_is_ge_now_and_aligned():
    interval = 10_000
    phase = 3_000
    now = 12_345
    due = compute_next_due_ms(now, interval, phase)
    assert due >= now
    assert due % interval == phase


def test_compute_next_due_advances_when_past_phase():
    # now just past the aligned tick → next due should be in the next window
    interval = 10_000
    phase = 1_000
    now = 1_500
    due = compute_next_due_ms(now, interval, phase)
    assert due == 11_000


def test_compute_next_due_exact_alignment():
    assert compute_next_due_ms(10_000, 10_000, 0) == 10_000


def test_is_within_active_hours_none_always_true():
    now = datetime(2026, 4, 14, 3, 0, tzinfo=timezone.utc)
    assert is_within_active_hours(now, None) is True


def test_is_within_active_hours_normal_window():
    ah = ActiveHours(start="08:00", end="17:00")
    inside = datetime(2026, 4, 14, 12, 0)
    before = datetime(2026, 4, 14, 7, 0)
    after = datetime(2026, 4, 14, 18, 0)
    assert is_within_active_hours(inside, ah) is True
    assert is_within_active_hours(before, ah) is False
    assert is_within_active_hours(after, ah) is False


def test_is_within_active_hours_wrap_around():
    ah = ActiveHours(start="22:00", end="06:00")
    late_night = datetime(2026, 4, 14, 23, 30)
    early_morning = datetime(2026, 4, 14, 3, 0)
    midday = datetime(2026, 4, 14, 12, 0)
    assert is_within_active_hours(late_night, ah) is True
    assert is_within_active_hours(early_morning, ah) is True
    assert is_within_active_hours(midday, ah) is False
