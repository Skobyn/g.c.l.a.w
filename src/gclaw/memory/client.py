"""Vertex AI Memory Bank REST API client.

Uses google.auth for credentials and httpx for async HTTP calls.
The Memory Bank API provides three key operations:
- memories:generate — extract facts from conversation text
- memories:retrieve — semantic search for relevant memories
- memories:list — list all memories for a scope

API docs: https://cloud.google.com/vertex-ai/docs/reference/rest/v1beta1/memoryBanks
"""

from __future__ import annotations

from typing import Any

import httpx
from google.auth.credentials import Credentials
from google.auth.transport.requests import Request as AuthRequest

from gclaw.models.memory import Memory, MemoryScope


class MemoryBankClient:
    """Async client for Vertex AI Memory Bank REST API."""

    def __init__(
        self,
        project_id: str,
        location: str,
        credentials: Credentials,
        memory_bank_id: str = "default",
    ) -> None:
        self._project_id = project_id
        self._location = location
        self._credentials = credentials
        self._memory_bank_id = memory_bank_id
        self._base_url = (
            f"https://{location}-aiplatform.googleapis.com/v1beta1/"
            f"projects/{project_id}/locations/{location}/"
            f"memoryBanks/{memory_bank_id}"
        )

    def _get_headers(self) -> dict[str, str]:
        """Get auth headers, refreshing credentials if needed."""
        if not self._credentials.valid:
            self._credentials.refresh(AuthRequest())
        return {
            "Authorization": f"Bearer {self._credentials.token}",
            "Content-Type": "application/json",
        }

    async def _post(self, url: str, json: dict) -> httpx.Response:
        """Make an authenticated POST request."""
        headers = self._get_headers()
        async with httpx.AsyncClient() as http:
            response = await http.post(url, json=json, headers=headers)
            response.raise_for_status()
            return response

    def _build_scope_dict(self, scope: MemoryScope) -> dict[str, str]:
        """Build the scope dict for the API request."""
        d: dict[str, str] = {"user_id": scope.user_id}
        if scope.agent is not None:
            d["agent"] = scope.agent
        return d

    async def generate_memories(
        self,
        scope: MemoryScope,
        conversation_text: str,
        topics: list[str] | None = None,
    ) -> list[Memory]:
        """Extract memories from conversation text via memories:generate.

        Args:
            scope: Memory scope (user or user+agent).
            conversation_text: The conversation to extract facts from.
            topics: Optional list of topics to focus extraction on.

        Returns:
            List of extracted Memory objects.
        """
        body: dict[str, Any] = {
            "scope": self._build_scope_dict(scope),
            "conversation": {"text": conversation_text},
        }
        if topics:
            body["topics"] = topics

        url = f"{self._base_url}/memories:generate"
        response = await self._post(url, json=body)
        data = response.json()

        memories = []
        for item in data.get("generatedMemories", []):
            mem_data = item.get("memory", {})
            memories.append(
                Memory(
                    fact=mem_data.get("fact", ""),
                    topic=mem_data.get("topic", ""),
                    update_time=mem_data.get("updateTime"),
                )
            )
        return memories

    async def retrieve_memories(
        self,
        scope: MemoryScope,
        query: str,
        top_k: int = 10,
    ) -> list[Memory]:
        """Retrieve relevant memories via semantic search.

        Args:
            scope: Memory scope (user or user+agent).
            query: Natural language query to search against.
            top_k: Maximum number of memories to return.

        Returns:
            List of Memory objects sorted by relevance.
        """
        body: dict[str, Any] = {
            "scope": self._build_scope_dict(scope),
            "query": query,
            "topK": top_k,
        }

        url = f"{self._base_url}/memories:retrieve"
        response = await self._post(url, json=body)
        data = response.json()

        memories = []
        for item in data.get("memories", []):
            memories.append(
                Memory(
                    fact=item.get("fact", ""),
                    topic=item.get("topic", ""),
                    update_time=item.get("updateTime"),
                    score=item.get("score"),
                )
            )
        return memories

    async def list_memories(
        self,
        scope: MemoryScope,
    ) -> list[Memory]:
        """List all memories for a given scope.

        Args:
            scope: Memory scope (user or user+agent).

        Returns:
            List of all Memory objects in the scope.
        """
        body: dict[str, Any] = {
            "scope": self._build_scope_dict(scope),
        }

        url = f"{self._base_url}/memories:list"
        response = await self._post(url, json=body)
        data = response.json()

        memories = []
        for item in data.get("memories", []):
            memories.append(
                Memory(
                    fact=item.get("fact", ""),
                    topic=item.get("topic", ""),
                    update_time=item.get("updateTime"),
                )
            )
        return memories

    async def delete_memory(
        self,
        scope: MemoryScope,
        fact: str,
    ) -> None:
        """Delete a specific memory from the Memory Bank.

        Args:
            scope: Memory scope (user or user+agent).
            fact: The exact fact text of the memory to delete.
        """
        body: dict[str, Any] = {
            "scope": self._build_scope_dict(scope),
            "fact": fact,
        }

        url = f"{self._base_url}/memories:delete"
        await self._post(url, json=body)
