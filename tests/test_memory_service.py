"""Tests for memory service — auto-recall, auto-capture, scoping."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from gclaw.models.memory import Memory, MemoryScope
from gclaw.memory.service import MemoryService


@pytest.fixture
def memory_client():
    client = MagicMock()
    client.retrieve_memories = AsyncMock(return_value=[])
    client.generate_memories = AsyncMock(return_value=[])
    client.list_memories = AsyncMock(return_value=[])
    return client


@pytest.fixture
def service(memory_client):
    return MemoryService(client=memory_client)


@pytest.mark.asyncio
async def test_recall_user_scoped(service, memory_client):
    """Auto-recall retrieves memories for user scope."""
    memory_client.retrieve_memories.return_value = [
        Memory(fact="User prefers dark mode", topic="USER_PREFERENCES", score=0.95),
        Memory(fact="User's name is Sam", topic="KEY_CONVERSATION_DETAILS", score=0.88),
    ]

    memories = await service.recall(
        user_id="user_123",
        query="What are the user's preferences?",
    )

    assert len(memories) == 2
    assert memories[0].fact == "User prefers dark mode"
    memory_client.retrieve_memories.assert_awaited_once()
    # Should use user-scoped
    call_args = memory_client.retrieve_memories.call_args
    assert call_args.kwargs["scope"].user_id == "user_123"
    assert call_args.kwargs["scope"].agent is None


@pytest.mark.asyncio
async def test_recall_agent_scoped(service, memory_client):
    """Auto-recall can include agent-specific memories."""
    memory_client.retrieve_memories.return_value = [
        Memory(fact="Email sign-off: Best regards", topic="USER_PREFERENCES", score=0.90),
    ]

    memories = await service.recall(
        user_id="user_123",
        query="email style",
        agent_id="workspace-mgr",
    )

    assert len(memories) == 1
    call_args = memory_client.retrieve_memories.call_args
    assert call_args.kwargs["scope"].agent == "workspace-mgr"


@pytest.mark.asyncio
async def test_recall_merged_scopes(service, memory_client):
    """When agent_id is set, recall merges both user-scoped and agent-scoped."""
    user_memories = [
        Memory(fact="User prefers dark mode", topic="USER_PREFERENCES", score=0.95),
    ]
    agent_memories = [
        Memory(fact="Email sign-off: Best", topic="USER_PREFERENCES", score=0.90),
    ]
    # First call = agent-scoped, second call = user-scoped
    memory_client.retrieve_memories.side_effect = [agent_memories, user_memories]

    memories = await service.recall(
        user_id="user_123",
        query="preferences",
        agent_id="workspace-mgr",
        merge_user_scope=True,
    )

    # Should have merged both scopes
    assert len(memories) == 2
    assert memory_client.retrieve_memories.await_count == 2


@pytest.mark.asyncio
async def test_capture_fires_generate(service, memory_client):
    """Auto-capture sends conversation to memories:generate."""
    memory_client.generate_memories.return_value = [
        Memory(fact="User likes coffee", topic="USER_PREFERENCES"),
    ]

    result = await service.capture(
        user_id="user_123",
        conversation_text="User: I really like coffee\nAgent: Noted!",
    )

    assert len(result) == 1
    memory_client.generate_memories.assert_awaited_once()


@pytest.mark.asyncio
async def test_capture_with_agent_scope(service, memory_client):
    """Auto-capture can target agent-specific scope."""
    memory_client.generate_memories.return_value = []

    await service.capture(
        user_id="user_123",
        conversation_text="Some conversation",
        agent_id="dev-mgr",
    )

    call_args = memory_client.generate_memories.call_args
    assert call_args.kwargs["scope"].agent == "dev-mgr"


@pytest.mark.asyncio
async def test_capture_with_topics(service, memory_client):
    """Auto-capture can specify topics to focus on."""
    memory_client.generate_memories.return_value = []

    await service.capture(
        user_id="user_123",
        conversation_text="Working on Q2 roadmap",
        topics=["project_context", "action_items"],
    )

    call_args = memory_client.generate_memories.call_args
    assert call_args.kwargs["topics"] == ["project_context", "action_items"]


@pytest.mark.asyncio
async def test_generate_memories_delegates(service, memory_client):
    """generate_memories is the end-of-session extraction call."""
    memory_client.generate_memories.return_value = [
        Memory(fact="Important fact", topic="KEY_CONVERSATION_DETAILS"),
    ]

    result = await service.generate_memories(
        user_id="user_123",
        conversation_text="Full session text here",
    )

    assert len(result) == 1
    memory_client.generate_memories.assert_awaited_once()


@pytest.mark.asyncio
async def test_capture_error_is_suppressed(service, memory_client):
    """Auto-capture errors should not propagate (fire-and-forget)."""
    memory_client.generate_memories.side_effect = Exception("API error")

    # Should not raise
    result = await service.capture(
        user_id="user_123",
        conversation_text="Some text",
    )

    assert result == []


@pytest.mark.asyncio
async def test_format_memories_for_prompt(service):
    """Format memories into injectable prompt text."""
    memories = [
        Memory(fact="User prefers dark mode", topic="USER_PREFERENCES"),
        Memory(fact="User works at Acme", topic="KEY_CONVERSATION_DETAILS"),
    ]

    formatted = service.format_for_prompt(memories)

    assert "User prefers dark mode" in formatted
    assert "User works at Acme" in formatted
    assert "USER_PREFERENCES" in formatted


def test_format_memories_empty(service):
    """format_for_prompt returns empty string for no memories."""
    assert service.format_for_prompt([]) == ""
