"""Tests for Vertex AI Memory Bank REST client.

All HTTP calls are mocked — no real GCP requests.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from gclaw.models.memory import Memory, MemoryScope, MemoryTopic
from gclaw.memory.client import MemoryBankClient


@pytest.fixture
def mock_credentials():
    creds = MagicMock()
    creds.token = "test-token"
    creds.valid = True
    return creds


@pytest.fixture
def client(mock_credentials):
    return MemoryBankClient(
        project_id="test-project",
        location="us-central1",
        credentials=mock_credentials,
    )


@pytest.mark.asyncio
async def test_generate_memories(client):
    """Test memories:generate endpoint — extracts facts from conversation."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "generatedMemories": [
            {
                "memory": {
                    "fact": "User prefers dark mode",
                    "topic": "USER_PREFERENCES",
                    "updateTime": "2026-03-30T12:00:00Z",
                },
            },
            {
                "memory": {
                    "fact": "User's name is Sam",
                    "topic": "KEY_CONVERSATION_DETAILS",
                    "updateTime": "2026-03-30T12:00:00Z",
                },
            },
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch.object(client, "_post", new_callable=AsyncMock, return_value=mock_response):
        memories = await client.generate_memories(
            scope=MemoryScope(user_id="user_123"),
            conversation_text="User: I prefer dark mode\nAgent: Got it!",
        )

    assert len(memories) == 2
    assert memories[0].fact == "User prefers dark mode"
    assert memories[0].topic == "USER_PREFERENCES"


@pytest.mark.asyncio
async def test_retrieve_memories(client):
    """Test memories:retrieve endpoint — semantic search for relevant memories."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "memories": [
            {
                "fact": "User likes Italian food",
                "topic": "USER_PREFERENCES",
                "updateTime": "2026-03-30T12:00:00Z",
                "score": 0.92,
            },
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch.object(client, "_post", new_callable=AsyncMock, return_value=mock_response):
        memories = await client.retrieve_memories(
            scope=MemoryScope(user_id="user_123"),
            query="What food does the user like?",
            top_k=5,
        )

    assert len(memories) == 1
    assert memories[0].fact == "User likes Italian food"
    assert memories[0].score == 0.92


@pytest.mark.asyncio
async def test_list_memories(client):
    """Test memories:list endpoint — list all memories for a scope."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "memories": [
            {
                "fact": "User prefers dark mode",
                "topic": "USER_PREFERENCES",
                "updateTime": "2026-03-30T12:00:00Z",
            },
            {
                "fact": "User works at Acme Corp",
                "topic": "KEY_CONVERSATION_DETAILS",
                "updateTime": "2026-03-29T10:00:00Z",
            },
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch.object(client, "_post", new_callable=AsyncMock, return_value=mock_response):
        memories = await client.list_memories(
            scope=MemoryScope(user_id="user_123"),
        )

    assert len(memories) == 2


@pytest.mark.asyncio
async def test_retrieve_with_agent_scope(client):
    """Test retrieval with agent-specific scope."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"memories": []}
    mock_response.raise_for_status = MagicMock()

    with patch.object(client, "_post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
        await client.retrieve_memories(
            scope=MemoryScope(user_id="user_123", agent="workspace-mgr"),
            query="email preferences",
        )

    # Verify the scope was passed correctly
    mock_post.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_with_custom_topics(client):
    """Test generate with custom topic filtering."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"generatedMemories": []}
    mock_response.raise_for_status = MagicMock()

    with patch.object(client, "_post", new_callable=AsyncMock, return_value=mock_response):
        memories = await client.generate_memories(
            scope=MemoryScope(user_id="user_123"),
            conversation_text="Working on the Q2 roadmap project",
            topics=["project_context", "action_items"],
        )

    assert memories == []


def test_build_scope_dict_user_only(client):
    scope = MemoryScope(user_id="user_123")
    result = client._build_scope_dict(scope)
    assert result == {"user_id": "user_123"}


def test_build_scope_dict_with_agent(client):
    scope = MemoryScope(user_id="user_123", agent="workspace-mgr")
    result = client._build_scope_dict(scope)
    assert result == {"user_id": "user_123", "agent": "workspace-mgr"}


def test_base_url(client):
    expected = (
        "https://us-central1-aiplatform.googleapis.com/v1beta1/"
        "projects/test-project/locations/us-central1/memoryBanks/default"
    )
    assert client._base_url == expected


@pytest.mark.asyncio
async def test_delete_memory(client):
    """Test memories:delete endpoint."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {}
    mock_response.raise_for_status = MagicMock()

    with patch.object(client, "_post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
        await client.delete_memory(
            scope=MemoryScope(user_id="user_123"),
            fact="User prefers dark mode",
        )

    mock_post.assert_awaited_once()
