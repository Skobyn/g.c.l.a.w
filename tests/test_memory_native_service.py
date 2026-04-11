"""Tests for NativeMemoryService — the ADK-backed MemoryService variant.

All ADK calls are mocked — no real GCP requests.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from gclaw.memory.native_service import NativeMemoryService
from gclaw.models.memory import Memory


def _entry(text: str, timestamp: str = "2026-04-11T10:00:00Z"):
    """Build a duck-typed ADK MemoryEntry — content.parts[0].text + timestamp."""
    return SimpleNamespace(
        content=SimpleNamespace(
            parts=[SimpleNamespace(text=text)],
        ),
        timestamp=timestamp,
    )


def _response(entries):
    return SimpleNamespace(memories=entries)


@pytest.fixture
def native():
    """Fake VertexAiMemoryBankService with async stubs."""
    svc = MagicMock()
    svc.search_memory = AsyncMock(return_value=_response([]))
    svc.add_events_to_memory = AsyncMock(return_value=None)
    return svc


@pytest.fixture
def service(native):
    return NativeMemoryService(native=native, app_name="gclaw")


# ---------------------------------------------------------------------------
# recall
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recall_user_scope_uses_base_app_name(service, native):
    native.search_memory.return_value = _response([
        _entry("User likes dark mode"),
    ])

    memories = await service.recall(user_id="u1", query="preferences")

    native.search_memory.assert_awaited_once_with(
        app_name="gclaw",
        user_id="u1",
        query="preferences",
    )
    assert len(memories) == 1
    assert memories[0].fact == "User likes dark mode"


@pytest.mark.asyncio
async def test_recall_agent_scope_partitions_app_name(service, native):
    native.search_memory.return_value = _response([
        _entry("PR review style: concise"),
    ])

    await service.recall(user_id="u1", query="review style", agent_id="dev-mgr")

    native.search_memory.assert_awaited_once_with(
        app_name="gclaw/dev-mgr",
        user_id="u1",
        query="review style",
    )


@pytest.mark.asyncio
async def test_recall_merge_user_scope_dedupes(service, native):
    """merge_user_scope=True does a second call against the base app
    partition and dedupes by fact text."""
    agent_response = _response([
        _entry("Agent-scoped fact A"),
        _entry("Shared fact"),
    ])
    user_response = _response([
        _entry("User-scoped fact B"),
        _entry("Shared fact"),  # duplicate — should be deduped
    ])
    native.search_memory = AsyncMock(side_effect=[agent_response, user_response])

    memories = await service.recall(
        user_id="u1",
        query="q",
        agent_id="dev-mgr",
        merge_user_scope=True,
    )

    facts = [m.fact for m in memories]
    assert facts == ["Agent-scoped fact A", "Shared fact", "User-scoped fact B"]
    assert native.search_memory.await_count == 2


@pytest.mark.asyncio
async def test_recall_respects_top_k(service, native):
    native.search_memory.return_value = _response([
        _entry(f"Fact {i}") for i in range(20)
    ])
    memories = await service.recall(user_id="u1", query="q", top_k=5)
    assert len(memories) == 5


@pytest.mark.asyncio
async def test_recall_swallows_search_exceptions(service, native):
    native.search_memory = AsyncMock(side_effect=RuntimeError("backend down"))
    memories = await service.recall(user_id="u1", query="q")
    assert memories == []


# ---------------------------------------------------------------------------
# capture
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_capture_translates_conversation_to_events(service, native):
    text = "User: I prefer terse responses\nAgent: Got it."

    result = await service.capture(user_id="u1", conversation_text=text)

    assert result == []
    native.add_events_to_memory.assert_awaited_once()
    kwargs = native.add_events_to_memory.call_args.kwargs
    assert kwargs["app_name"] == "gclaw"
    assert kwargs["user_id"] == "u1"

    events = kwargs["events"]
    assert len(events) == 2
    # The user event
    assert events[0].content.role == "user"
    assert events[0].content.parts[0].text == "I prefer terse responses"
    # The agent event
    assert events[1].content.role == "model"
    assert events[1].content.parts[0].text == "Got it."


@pytest.mark.asyncio
async def test_capture_with_agent_id_partitions_app(service, native):
    await service.capture(
        user_id="u1",
        conversation_text="User: hi\nAgent: hey",
        agent_id="comms-mgr",
    )

    kwargs = native.add_events_to_memory.call_args.kwargs
    assert kwargs["app_name"] == "gclaw/comms-mgr"


@pytest.mark.asyncio
async def test_capture_passes_topics_as_custom_metadata(service, native):
    await service.capture(
        user_id="u1",
        conversation_text="User: hi\nAgent: ok",
        topics=["USER_PREFERENCES", "ROUTINES"],
    )
    kwargs = native.add_events_to_memory.call_args.kwargs
    assert kwargs["custom_metadata"] == {
        "topics": ["USER_PREFERENCES", "ROUTINES"]
    }


@pytest.mark.asyncio
async def test_capture_without_topics_sends_no_metadata(service, native):
    await service.capture(user_id="u1", conversation_text="User: hi\nAgent: ok")
    kwargs = native.add_events_to_memory.call_args.kwargs
    assert kwargs["custom_metadata"] is None


@pytest.mark.asyncio
async def test_capture_empty_text_is_noop(service, native):
    result = await service.capture(user_id="u1", conversation_text="")
    assert result == []
    native.add_events_to_memory.assert_not_awaited()


@pytest.mark.asyncio
async def test_capture_swallows_exceptions(service, native):
    native.add_events_to_memory = AsyncMock(side_effect=RuntimeError("backend down"))
    # Must not raise.
    result = await service.capture(user_id="u1", conversation_text="User: hi")
    assert result == []


# ---------------------------------------------------------------------------
# generate_memories (end-of-session, raises on error)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_memories_uses_same_event_path(service, native):
    await service.generate_memories(
        user_id="u1",
        conversation_text="User: hello\nAgent: hi",
    )
    native.add_events_to_memory.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_memories_raises_on_error(service, native):
    native.add_events_to_memory = AsyncMock(side_effect=RuntimeError("backend down"))
    with pytest.raises(RuntimeError, match="backend down"):
        await service.generate_memories(
            user_id="u1", conversation_text="User: hi"
        )


# ---------------------------------------------------------------------------
# format_for_prompt delegates to MemoryService.format_for_prompt
# ---------------------------------------------------------------------------


def test_format_for_prompt_delegates(service):
    memories = [
        Memory(fact="high", topics=["USER_PREFERENCES"], importance=0.9),
        Memory(fact="low", topics=["USER_PREFERENCES"], importance=0.2),
    ]
    formatted = service.format_for_prompt(memories)
    assert "**USER_PREFERENCES:**" in formatted
    # Importance-sorted within the group.
    high_pos = formatted.index("high")
    low_pos = formatted.index("low")
    assert high_pos < low_pos


# ---------------------------------------------------------------------------
# shared channel (best-effort shim)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recall_shared_partitions_by_channel(service, native):
    native.search_memory.return_value = _response([_entry("shared fact")])
    memories = await service.recall_shared(
        shared_channel="userA__userB", query="q"
    )

    kwargs = native.search_memory.call_args.kwargs
    assert kwargs["app_name"] == "gclaw/shared/userA__userB"
    assert kwargs["user_id"] == "shared"
    assert [m.fact for m in memories] == ["shared fact"]
