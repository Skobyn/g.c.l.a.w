"""Memory service — auto-recall, auto-capture, and scoping logic.

This service wraps the MemoryBankClient and provides higher-level
operations used by the AgentRunner and HeartbeatContextGatherer:

- recall: retrieve relevant memories before an agent turn
- capture: extract facts from conversation after a turn (fire-and-forget)
- generate_memories: full extraction at end of session
- format_for_prompt: format memories for injection into system prompts
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from gclaw.models.memory import Memory, MemoryScope

if TYPE_CHECKING:
    from gclaw.memory.client import MemoryBankClient

logger = logging.getLogger(__name__)


class MemoryService:
    """High-level memory operations with scoping and error handling."""

    def __init__(self, client: MemoryBankClient) -> None:
        self._client = client

    async def recall(
        self,
        user_id: str,
        query: str,
        agent_id: str | None = None,
        top_k: int = 10,
        merge_user_scope: bool = False,
    ) -> list[Memory]:
        """Auto-recall: retrieve relevant memories before an agent turn.

        Args:
            user_id: The user to retrieve memories for.
            query: Natural language query (typically the user's message).
            agent_id: If set, retrieve from agent-scoped memories.
            top_k: Max memories to return per scope.
            merge_user_scope: If True and agent_id is set, also retrieve
                user-scoped memories and merge the results.

        Returns:
            List of relevant Memory objects sorted by score.
        """
        if agent_id and merge_user_scope:
            # Retrieve from both agent scope and user scope
            agent_scope = MemoryScope(user_id=user_id, agent=agent_id)
            user_scope = MemoryScope(user_id=user_id)

            agent_memories = await self._client.retrieve_memories(
                scope=agent_scope, query=query, top_k=top_k,
            )
            user_memories = await self._client.retrieve_memories(
                scope=user_scope, query=query, top_k=top_k,
            )

            # Merge and deduplicate by fact text
            seen: set[str] = set()
            merged: list[Memory] = []
            for m in agent_memories + user_memories:
                if m.fact not in seen:
                    seen.add(m.fact)
                    merged.append(m)
            return merged

        scope = MemoryScope(user_id=user_id, agent=agent_id)
        return await self._client.retrieve_memories(
            scope=scope, query=query, top_k=top_k,
        )

    async def capture(
        self,
        user_id: str,
        conversation_text: str,
        agent_id: str | None = None,
        topics: list[str] | None = None,
    ) -> list[Memory]:
        """Auto-capture: fire-and-forget extraction after each turn.

        Errors are logged and suppressed — capture should never break
        the main conversation flow.

        Args:
            user_id: The user to store memories for.
            conversation_text: Text of the recent exchange.
            agent_id: If set, store in agent-scoped memories.
            topics: Optional topics to focus extraction on.

        Returns:
            List of extracted memories (empty on error).
        """
        try:
            scope = MemoryScope(user_id=user_id, agent=agent_id)
            return await self._client.generate_memories(
                scope=scope,
                conversation_text=conversation_text,
                topics=topics,
            )
        except Exception:
            logger.warning(
                "Memory capture failed for user %s (agent=%s)",
                user_id,
                agent_id,
                exc_info=True,
            )
            return []

    async def generate_memories(
        self,
        user_id: str,
        conversation_text: str,
        agent_id: str | None = None,
    ) -> list[Memory]:
        """End-of-session memory extraction.

        Unlike capture(), this raises on error — callers should handle it.

        Args:
            user_id: The user to store memories for.
            conversation_text: Full session conversation text.
            agent_id: If set, store in agent-scoped memories.

        Returns:
            List of extracted memories.
        """
        scope = MemoryScope(user_id=user_id, agent=agent_id)
        return await self._client.generate_memories(
            scope=scope,
            conversation_text=conversation_text,
        )

    def format_for_prompt(self, memories: list[Memory]) -> str:
        """Format memories into text suitable for system prompt injection.

        Groups memories by topic for readability.
        """
        if not memories:
            return ""

        # Group by topic
        by_topic: dict[str, list[str]] = {}
        for m in memories:
            topic = m.topic or "general"
            if topic not in by_topic:
                by_topic[topic] = []
            by_topic[topic].append(m.fact)

        lines: list[str] = []
        for topic, facts in by_topic.items():
            lines.append(f"**{topic}:**")
            for fact in facts:
                lines.append(f"- {fact}")
            lines.append("")

        return "\n".join(lines).strip()
