"""Three-tier context compaction inspired by Claude Code's compression system.

Tiers:
1. MicroCompact — drop old messages, keep recent. Zero API cost.
2. AutoCompact — LLM-generated summary when approaching limit.
3. FullCompact — complete reset with selective re-injection.

Includes a circuit breaker to prevent runaway compression attempts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class CompactionStrategy(str, Enum):
    MICRO = "micro"
    AUTO = "auto"
    FULL = "full"


@dataclass
class CompactionResult:
    strategy: CompactionStrategy
    messages_before: int
    messages_after: int
    summary: str | None = None
    kept_messages: list[str] = field(default_factory=list)
    tokens_saved: int = 0


class ContextCompactor:
    """Selects and executes context compaction strategies."""

    def __init__(
        self,
        micro_threshold: int = 30,
        auto_threshold: int = 50,
        full_threshold: int = 80,
        max_consecutive_failures: int = 3,
    ) -> None:
        self._micro = micro_threshold
        self._auto = auto_threshold
        self._full = full_threshold
        self._max_failures = max_consecutive_failures
        self._consecutive_failures = 0

    @property
    def circuit_open(self) -> bool:
        return self._consecutive_failures >= self._max_failures

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        if self.circuit_open:
            logger.warning(
                "Compaction circuit breaker tripped after %d failures",
                self._consecutive_failures,
            )

    def record_success(self) -> None:
        self._consecutive_failures = 0

    def select_strategy(self, message_count: int) -> CompactionStrategy | None:
        if message_count >= self._full:
            return CompactionStrategy.FULL
        if message_count >= self._auto:
            return CompactionStrategy.AUTO
        if message_count >= self._micro:
            return CompactionStrategy.MICRO
        return None

    def micro_compact(
        self,
        messages: list[str],
        keep_recent: int = 20,
        preserve_system: bool = False,
    ) -> CompactionResult:
        before = len(messages)

        if preserve_system and messages:
            system = [messages[0]]
            recent = messages[-keep_recent:]
            kept = system + recent
        else:
            kept = messages[-keep_recent:]

        return CompactionResult(
            strategy=CompactionStrategy.MICRO,
            messages_before=before,
            messages_after=len(kept),
            kept_messages=kept,
        )
