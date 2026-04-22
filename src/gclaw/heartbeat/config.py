"""Per-agent heartbeat configuration model and duration parser."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field


class ActiveHours(BaseModel):
    """Window of local time during which heartbeats should fire."""

    start: str  # "HH:MM"
    end: str  # "HH:MM"
    timezone: str = "UTC"


class HeartbeatConfig(BaseModel):
    """Per-agent heartbeat config.

    Controls the periodic "wake-up" that lets an agent reason about
    what needs attention without a user turn.
    """

    enabled: bool = False
    every: str = "30m"
    prompt: str | None = None
    session: str = "main"
    isolated_session: bool = False
    light_context: bool = False
    timeout_seconds: int = 120
    ack_max_chars: int = 30
    active_hours: ActiveHours | None = None
    target: Literal["none", "last", "channel"] = "none"
    channel: str | None = None
    include_reasoning: bool = False


# Unit → milliseconds multiplier. Order matters for longest-prefix parsing
# (ms before m).
_UNIT_MS: dict[str, int] = {
    "ms": 1,
    "s": 1_000,
    "m": 60_000,
    "h": 3_600_000,
    "d": 86_400_000,
}

# Match: optional sign (disallowed for duration, but captured to error
# clearly), digits (with optional decimal), optional unit suffix.
_DURATION_RE = re.compile(
    r"^\s*(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>ms|s|m|h|d)?\s*$",
    re.IGNORECASE,
)


def parse_duration_ms(s: str) -> int:
    """Parse duration string like '30m', '2h', '500ms' into milliseconds.

    Supported units: ms, s, m, h, d. If no unit is provided, defaults to
    minutes. Raises ValueError for invalid input.
    """
    if not isinstance(s, str):
        raise ValueError(f"duration must be a string, got {type(s).__name__}")

    match = _DURATION_RE.match(s)
    if not match:
        raise ValueError(f"invalid duration: {s!r}")

    num = float(match.group("num"))
    unit = (match.group("unit") or "m").lower()

    if unit not in _UNIT_MS:
        # Defensive — regex already restricts units.
        raise ValueError(f"unknown duration unit: {unit!r}")

    return int(num * _UNIT_MS[unit])
