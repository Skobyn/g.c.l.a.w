"""Memory service — auto-recall, auto-capture, and scoping logic.

This service wraps the MemoryBankClient and provides higher-level
operations used by the AgentRunner and HeartbeatContextGatherer:

- recall: retrieve relevant memories before an agent turn
- capture: extract facts from conversation after a turn (fire-and-forget)
- generate_memories: full extraction at end of session
- format_for_prompt: format memories for injection into system prompts
- wipe_user_memories: delete every memory for a user (governance)

All ingestion paths (capture, generate_memories) run conversation
text through the PII scrubber (gclaw.memory.pii) before handing
it off to Memory Bank, so secrets, credit cards, and other common
PII categories never land in long-term storage.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from gclaw.memory.pii import scrub_pii
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

    async def recall_shared(
        self,
        shared_channel: str,
        query: str,
        top_k: int = 10,
    ) -> list[Memory]:
        """Retrieve memories from a shared cross-user channel.

        Args:
            shared_channel: The shared channel identifier (e.g. "userA__userB").
            query: Natural language query.
            top_k: Max memories to return.

        Returns:
            List of relevant Memory objects from the shared scope.
        """
        scope = MemoryScope(
            user_id="",  # Not user-specific
            shared_channel=shared_channel,
        )
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

        The conversation text is run through the PII scrubber before
        being handed off to Memory Bank — secrets, emails, phone
        numbers, credit cards, and similar categories never land in
        long-term storage. Scrub counts are logged at INFO when
        anything was redacted.

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
        scrubbed, report = scrub_pii(conversation_text)
        if report:
            logger.info(
                "PII scrubbed before capture for user %s: %s", user_id, report
            )
        try:
            scope = MemoryScope(user_id=user_id, agent=agent_id)
            return await self._client.generate_memories(
                scope=scope,
                conversation_text=scrubbed,
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
        PII is scrubbed before the text is handed off.

        Args:
            user_id: The user to store memories for.
            conversation_text: Full session conversation text.
            agent_id: If set, store in agent-scoped memories.

        Returns:
            List of extracted memories.
        """
        scrubbed, report = scrub_pii(conversation_text)
        if report:
            logger.info(
                "PII scrubbed before generate_memories for user %s: %s",
                user_id,
                report,
            )
        scope = MemoryScope(user_id=user_id, agent=agent_id)
        return await self._client.generate_memories(
            scope=scope,
            conversation_text=scrubbed,
        )

    async def wipe_user_memories(self, user_id: str) -> int:
        """Delete every memory for a user — the right-to-delete primitive.

        Lists all memories for the user scope and issues a delete for
        each. Individual delete failures are logged and counted; the
        method returns the total number of successful deletions.
        Callers (typically the admin DELETE /memory endpoint) can
        surface the count to the user.

        Note: this only wipes user-scope memories. Agent-scoped and
        shared-channel memories are NOT touched because they use
        different scopes that aren't enumerable via a single list call.
        A fuller implementation would iterate known agents and
        shared channels too — deferred as a follow-up.
        """
        scope = MemoryScope(user_id=user_id)
        try:
            memories = await self._client.list_memories(scope=scope)
        except Exception:
            logger.warning(
                "wipe_user_memories: list_memories failed for %s",
                user_id,
                exc_info=True,
            )
            return 0

        deleted = 0
        for m in memories:
            if not m.fact:
                continue
            try:
                await self._client.delete_memory(scope=scope, fact=m.fact)
                deleted += 1
            except Exception:
                logger.warning(
                    "wipe_user_memories: delete failed for user %s fact=%r",
                    user_id,
                    m.fact[:60],
                    exc_info=True,
                )
        logger.info(
            "wipe_user_memories: deleted %d/%d memories for user %s",
            deleted,
            len(memories),
            user_id,
        )
        return deleted

    def format_for_prompt(self, memories: list[Memory]) -> str:
        """Format memories into text suitable for system prompt injection.

        Groups memories by their primary topic (topics[0]) for
        readability and orders each group by importance descending —
        so the model sees the most salient memories first within each
        group. A memory with no topics lands in the "general" bucket.
        """
        if not memories:
            return ""

        def _primary_topic(m: Memory) -> str:
            return m.topics[0] if m.topics else "general"

        by_topic: dict[str, list[Memory]] = {}
        for m in memories:
            by_topic.setdefault(_primary_topic(m), []).append(m)

        lines: list[str] = []
        for topic, group in by_topic.items():
            group.sort(key=lambda mem: mem.importance, reverse=True)
            lines.append(f"**{topic}:**")
            for m in group:
                lines.append(f"- {m.fact}")
            lines.append("")

        return "\n".join(lines).strip()
