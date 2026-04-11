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


def test_format_memories_sorts_each_group_by_importance(service):
    """Within a topic group, higher-importance memories render first."""
    memories = [
        Memory(fact="low-signal fact", topics=["USER_PREFERENCES"], importance=0.2),
        Memory(fact="high-signal fact", topics=["USER_PREFERENCES"], importance=0.9),
        Memory(fact="medium-signal fact", topics=["USER_PREFERENCES"], importance=0.5),
    ]

    formatted = service.format_for_prompt(memories)

    # All three render, and the high-importance one appears before the low-importance one.
    high_pos = formatted.index("high-signal fact")
    medium_pos = formatted.index("medium-signal fact")
    low_pos = formatted.index("low-signal fact")
    assert high_pos < medium_pos < low_pos


def test_format_memories_no_topics_goes_to_general_bucket(service):
    memories = [
        Memory(fact="orphan fact", topics=[], importance=0.6),
    ]
    formatted = service.format_for_prompt(memories)
    assert "**general:**" in formatted
    assert "orphan fact" in formatted


# ---------------------------------------------------------------------------
# Governance: PII scrubbing + wipe_user_memories (Item 3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_capture_scrubs_pii_before_generate(service, memory_client):
    """capture() runs conversation text through scrub_pii — secrets
    never hit Memory Bank."""
    await service.capture(
        user_id="user_123",
        conversation_text="email me at sam@example.com with key sk-abc12345678901234567890",
    )

    call_args = memory_client.generate_memories.call_args
    sent_text = call_args.kwargs["conversation_text"]
    assert "[REDACTED_EMAIL]" in sent_text
    assert "[REDACTED_API_KEY]" in sent_text
    assert "sam@example.com" not in sent_text
    assert "sk-abc12345" not in sent_text


@pytest.mark.asyncio
async def test_generate_memories_scrubs_pii(service, memory_client):
    await service.generate_memories(
        user_id="user_123",
        conversation_text="call me at 415-555-0123",
    )
    sent_text = memory_client.generate_memories.call_args.kwargs["conversation_text"]
    assert "[REDACTED_PHONE]" in sent_text
    assert "415-555-0123" not in sent_text


@pytest.mark.asyncio
async def test_wipe_user_memories_lists_then_deletes(service, memory_client):
    memory_client.list_memories = AsyncMock(return_value=[
        Memory(fact="fact one"),
        Memory(fact="fact two"),
        Memory(fact="fact three"),
    ])
    memory_client.delete_memory = AsyncMock(return_value=None)

    deleted = await service.wipe_user_memories(user_id="user_123")

    assert deleted == 3
    assert memory_client.delete_memory.await_count == 3
    # List scope was user-only.
    list_scope = memory_client.list_memories.call_args.kwargs["scope"]
    assert list_scope.user_id == "user_123"
    assert list_scope.agent is None


@pytest.mark.asyncio
async def test_wipe_user_memories_skips_empty_facts(service, memory_client):
    memory_client.list_memories = AsyncMock(return_value=[
        Memory(fact="real"),
        Memory(fact=""),  # empty, skip
    ])
    memory_client.delete_memory = AsyncMock(return_value=None)

    deleted = await service.wipe_user_memories(user_id="user_123")
    assert deleted == 1


@pytest.mark.asyncio
async def test_wipe_user_memories_counts_only_successful_deletes(
    service, memory_client
):
    """Individual delete failures are logged and the count reflects
    successes only — the method doesn't abort on first failure."""
    memory_client.list_memories = AsyncMock(return_value=[
        Memory(fact="a"),
        Memory(fact="b"),
        Memory(fact="c"),
    ])

    async def _delete(scope, fact):
        if fact == "b":
            raise RuntimeError("transient")

    memory_client.delete_memory = AsyncMock(side_effect=_delete)

    deleted = await service.wipe_user_memories(user_id="user_123")
    assert deleted == 2  # a + c succeeded, b failed


@pytest.mark.asyncio
async def test_wipe_user_memories_returns_zero_on_list_failure(
    service, memory_client
):
    memory_client.list_memories = AsyncMock(side_effect=RuntimeError("down"))
    deleted = await service.wipe_user_memories(user_id="user_123")
    assert deleted == 0
