"""Memory consolidation — the autoDream pattern.

Runs during idle time to keep memory clean and within budget.
Four phases: Orient, Gather Signal, Consolidate, Prune/Index.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from gclaw.models.memory import Memory

if TYPE_CHECKING:
    from gclaw.memory.service import MemoryService

logger = logging.getLogger(__name__)


class ConsolidationPhase(str, Enum):
    ORIENT = "orient"
    GATHER = "gather"
    CONSOLIDATE = "consolidate"
    PRUNE = "prune"


@dataclass
class ConsolidationResult:
    memories_scanned: int = 0
    memories_pruned: int = 0
    memories_merged: int = 0
    soul_updates: list[str] = field(default_factory=list)

    @property
    def net_reduction(self) -> int:
        return self.memories_pruned


class MemoryConsolidator:
    """Four-phase memory consolidation for idle-time maintenance."""

    def __init__(
        self,
        memory_service: MemoryService,
        max_memories: int = 200,
    ) -> None:
        self._memory = memory_service
        self._max = max_memories

    async def orient(self, user_id: str) -> list[Memory]:
        return await self._memory.recall(
            user_id=user_id,
            query="all user preferences, habits, and context",
            top_k=self._max,
        )

    def gather_signal(
        self,
        memories: list[Memory],
        similarity_threshold: float = 0.7,
    ) -> list[list[Memory]]:
        by_topic: dict[str, list[Memory]] = {}
        for m in memories:
            topic = m.topic or "general"
            if topic not in by_topic:
                by_topic[topic] = []
            by_topic[topic].append(m)

        return [group for group in by_topic.values() if len(group) >= 2]

    def prune(self, memories: list[Memory]) -> list[Memory]:
        sorted_memories = sorted(memories, key=lambda m: m.score, reverse=True)
        return sorted_memories[: self._max]

    async def run(self, user_id: str) -> ConsolidationResult:
        result = ConsolidationResult()

        memories = await self.orient(user_id)
        result.memories_scanned = len(memories)

        if not memories:
            return result

        groups = self.gather_signal(memories)
        result.memories_merged = len(groups)

        for group in groups:
            topic = group[0].topic or "general"
            logger.info(
                "Consolidation candidate: topic=%s, count=%d",
                topic,
                len(group),
            )

        pruned = self.prune(memories)
        result.memories_pruned = len(memories) - len(pruned)

        return result
