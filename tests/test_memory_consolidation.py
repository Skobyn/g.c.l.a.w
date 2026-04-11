"""Tests for memory consolidation (autoDream pattern)."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from gclaw.memory.consolidation import (
    ConsolidationPhase,
    ConsolidationResult,
    MemoryConsolidator,
)
from gclaw.models.memory import Memory


def test_consolidation_phase_values():
    assert ConsolidationPhase.ORIENT == "orient"
    assert ConsolidationPhase.GATHER == "gather"
    assert ConsolidationPhase.CONSOLIDATE == "consolidate"
    assert ConsolidationPhase.PRUNE == "prune"


def test_consolidation_result():
    result = ConsolidationResult(
        memories_scanned=100,
        memories_pruned=20,
        memories_merged=5,
        soul_updates=[],
    )
    assert result.memories_scanned == 100
    assert result.net_reduction == 20


@pytest.mark.asyncio
async def test_orient_phase():
    memory_service = AsyncMock()
    memory_service.recall.return_value = [
        Memory(fact="User prefers dark mode", topic="preferences", score=0.9),
        Memory(fact="User prefers dark mode in apps", topic="preferences", score=0.8),
    ]

    consolidator = MemoryConsolidator(
        memory_service=memory_service,
        max_memories=200,
    )
    candidates = await consolidator.orient(user_id="user1")
    assert len(candidates) == 2


@pytest.mark.asyncio
async def test_gather_finds_duplicates():
    consolidator = MemoryConsolidator(
        memory_service=AsyncMock(),
        max_memories=200,
    )
    memories = [
        Memory(fact="User prefers dark mode", topic="preferences", score=0.9),
        Memory(fact="User prefers dark mode in apps", topic="preferences", score=0.8),
        Memory(fact="User works at Acme Corp", topic="context", score=0.7),
    ]
    groups = consolidator.gather_signal(memories, similarity_threshold=0.7)
    assert len(groups) >= 1


@pytest.mark.asyncio
async def test_prune_respects_max():
    consolidator = MemoryConsolidator(
        memory_service=AsyncMock(),
        max_memories=2,
    )
    memories = [
        Memory(fact="fact1", topic="a", score=0.9),
        Memory(fact="fact2", topic="b", score=0.5),
        Memory(fact="fact3", topic="c", score=0.3),
    ]
    pruned = consolidator.prune(memories)
    assert len(pruned) == 2
    assert pruned[0].score >= pruned[1].score
