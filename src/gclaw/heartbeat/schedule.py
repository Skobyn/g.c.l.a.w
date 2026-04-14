"""Phase-staggered heartbeat scheduling helpers.

These are pure functions — no I/O, no async — so they are trivially
testable and safe to call from any scheduler (Cloud Scheduler today,
in-process tomorrow).

The phase offset is a deterministic function of ``(seed, agent_id)``:
two agents that share the same interval still fire on different ticks,
preventing a thundering-herd when many agents happen to pick
``every: 30m``.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, time as dtime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gclaw.heartbeat.config import ActiveHours


def resolve_phase_ms(agent_id: str, interval_ms: int, seed: str) -> int:
    """Deterministic per-agent offset within the interval window.

    Returns a value in ``[0, interval_ms)``. Same ``(seed, agent_id,
    interval_ms)`` always produces the same phase; different agents get
    different phases even when they share an interval.
    """
    if interval_ms <= 0:
        return 0
    h = hashlib.sha256(f"{seed}:{agent_id}".encode("utf-8")).digest()
    n = int.from_bytes(h[:4], "big")
    return n % interval_ms


def compute_next_due_ms(now_ms: int, interval_ms: int, phase_ms: int) -> int:
    """Next due timestamp ``>= now_ms`` whose offset within the interval
    equals ``phase_ms``.

    If ``now_ms`` already sits exactly on a phase-aligned tick, that tick
    is returned (the caller decides whether to fire or advance).
    """
    if interval_ms <= 0:
        return now_ms
    phase = phase_ms % interval_ms
    base = (now_ms // interval_ms) * interval_ms + phase
    if base < now_ms:
        base += interval_ms
    return base


def _parse_hhmm(s: str) -> dtime:
    hh, mm = s.split(":")
    return dtime(hour=int(hh), minute=int(mm))


def is_within_active_hours(
    now_local: datetime, active_hours: "ActiveHours | None"
) -> bool:
    """True if ``active_hours`` is ``None`` OR ``now_local`` falls in
    ``[start, end]``.

    Handles wrap-around windows (e.g. ``start=22:00 end=06:00`` meaning
    "10pm through 6am"). Inclusive on both ends.

    ``now_local`` is expected to already be in the window's local timezone
    — timezone conversion is the caller's concern.
    """
    if active_hours is None:
        return True
    start = _parse_hhmm(active_hours.start)
    end = _parse_hhmm(active_hours.end)
    cur = now_local.time().replace(microsecond=0)

    if start <= end:
        # Normal window, e.g. 08:00–17:00.
        return start <= cur <= end
    # Wrap-around window, e.g. 22:00–06:00.
    return cur >= start or cur <= end
