"""Tests for heartbeat context integration with memories."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock

from gclaw.models.memory import Memory
from gclaw.heartbeat.context import HeartbeatContextGatherer


@pytest.fixture
def board_service():
    svc = MagicMock()
    svc.get_all_tasks.return_value = []
    return svc


@pytest.fixture
def cron_service():
    svc = MagicMock()
    svc.list_all.return_value = []
    return svc


@pytest.fixture
def memory_service():
    svc = MagicMock()
    svc.recall = AsyncMock(return_value=[
        Memory(fact="User has a meeting at 3pm", topic="ROUTINES"),
        Memory(fact="User asked to be reminded about the report", topic="ACTION_ITEMS"),
    ])
    svc.format_for_prompt = MagicMock(
        return_value="- User has a meeting at 3pm\n- User asked to be reminded about the report"
    )
    return svc


@pytest.fixture
def gatherer_with_memory(board_service, cron_service, memory_service):
    return HeartbeatContextGatherer(
        board_service=board_service,
        cron_service=cron_service,
        memory_service=memory_service,
        user_id="user_123",
    )


@pytest.fixture
def gatherer_without_memory(board_service, cron_service):
    return HeartbeatContextGatherer(
        board_service=board_service,
        cron_service=cron_service,
    )


@pytest.mark.asyncio
async def test_gather_includes_memories(gatherer_with_memory, memory_service):
    context = await gatherer_with_memory.gather_async()

    assert len(context["memories"]) == 2
    assert context["memories"][0].fact == "User has a meeting at 3pm"
    memory_service.recall.assert_awaited_once()


@pytest.mark.asyncio
async def test_gather_message_includes_memories(gatherer_with_memory, memory_service):
    message = await gatherer_with_memory.gather_as_message_async()

    assert "Relevant Memories" in message
    assert "User has a meeting at 3pm" in message


def test_gather_without_memory(gatherer_without_memory):
    """Sync gather still works without memory service."""
    context = gatherer_without_memory.gather()

    assert context["memories"] == []


def test_gather_message_without_memory(gatherer_without_memory):
    """Sync gather_as_message still works without memory service."""
    message = gatherer_without_memory.gather_as_message()

    assert "Relevant Memories" not in message


@pytest.mark.asyncio
async def test_memory_failure_does_not_break_gather(gatherer_with_memory, memory_service):
    """If memory recall fails, gather should still succeed."""
    memory_service.recall.side_effect = Exception("Memory Bank unavailable")

    context = await gatherer_with_memory.gather_async()

    assert context["memories"] == []
