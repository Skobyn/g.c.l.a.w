"""Wake-reason taxonomy for heartbeat ticks."""

from __future__ import annotations

from enum import Enum


class WakeReason(str, Enum):
    INTERVAL = "interval"          # scheduled interval tick
    MANUAL = "manual"              # POST /admin/heartbeat/trigger
    BOARD_EVENT = "board-event"    # board task state change
    CRON = "cron"                  # cron with wake_mode=next-heartbeat fired
    HOOK = "hook"                  # generic hook trigger
    RETRY = "retry"                # gated previously, retrying
    OTHER = "other"
