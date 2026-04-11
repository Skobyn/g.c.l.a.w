"""Memory service backed by ADK's native VertexAiMemoryBankService.

This is the migration target from Item E of the loose-ends plan. The
existing `MemoryService` + `MemoryBankClient` stack is ~200 LoC of
hand-rolled HTTP against the Memory Bank REST API. ADK ships a
`BaseMemoryService` implementation for the same backend —
`VertexAiMemoryBankService` — that handles auth, retries, scope
packing, and the event-to-memory conversion natively.

This class exposes the same public surface as `MemoryService`
(`recall`, `capture`, `generate_memories`, `format_for_prompt`) so
`AgentRunner` and the per-manager before_agent_callbacks don't need
to change. Callers can switch backends via the `MEMORY_BACKEND`
setting in `main.py`.

**Agent-scoped memory via app_name partitioning.** ADK's
`VertexAiMemoryBankService.search_memory(app_name, user_id, query)`
packs `{app_name, user_id}` into the Memory Bank scope. We encode
our `agent_id` into `app_name` as `"<base>/<agent_id>"` so
agent-scoped memories land in their own partition without losing
user-level scoping.

**Structured memory shape is partially preserved.** ADK's
`MemoryEntry` carries only `content.parts[0].text` + `timestamp`,
so the `summary`/`entities`/`topics`/`importance` fields from the
richer `Memory` model land as empty defaults. Recall-time ranking
falls back to Memory Bank's own semantic-similarity ordering.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from gclaw.models.memory import Memory, MemoryScope

if TYPE_CHECKING:
    from google.adk.memory.vertex_ai_memory_bank_service import (
        VertexAiMemoryBankService,
    )

logger = logging.getLogger(__name__)


class NativeMemoryService:
    """Drop-in replacement for MemoryService backed by ADK.

    Public interface mirrors MemoryService exactly. Callers that
    treat MemoryService as a duck-typed dependency (AgentRunner,
    per-manager recall callbacks, HeartbeatContextGatherer) work
    without modification.
    """

    def __init__(
        self,
        native: "VertexAiMemoryBankService",
        app_name: str = "gclaw",
    ) -> None:
        self._native = native
        self._base_app_name = app_name

    def _scope_app_name(self, agent_id: str | None) -> str:
        """Encode agent_id into app_name for Memory Bank partitioning."""
        if agent_id:
            return f"{self._base_app_name}/{agent_id}"
        return self._base_app_name

    async def recall(
        self,
        user_id: str,
        query: str,
        agent_id: str | None = None,
        top_k: int = 10,
        merge_user_scope: bool = False,
    ) -> list[Memory]:
        """Retrieve memories via ADK's native search_memory.

        When `merge_user_scope=True` and `agent_id` is set, searches
        both the agent partition and the user-level partition and
        dedupes by fact text — mirrors the old MemoryService.recall
        merge behaviour.
        """
        primary_app = self._scope_app_name(agent_id)
        try:
            response = await self._native.search_memory(
                app_name=primary_app,
                user_id=user_id,
                query=query,
            )
        except Exception:
            logger.warning(
                "Native search_memory failed for %s/%s",
                primary_app,
                user_id,
                exc_info=True,
            )
            return []

        primary = [self._entry_to_memory(e) for e in response.memories[:top_k]]

        if not (agent_id and merge_user_scope):
            return primary

        # Also pull user-level scope and merge.
        try:
            user_response = await self._native.search_memory(
                app_name=self._base_app_name,
                user_id=user_id,
                query=query,
            )
        except Exception:
            logger.warning(
                "Native search_memory (user scope merge) failed for %s",
                user_id,
                exc_info=True,
            )
            return primary

        seen: set[str] = {m.fact for m in primary}
        merged = list(primary)
        for entry in user_response.memories[:top_k]:
            m = self._entry_to_memory(entry)
            if m.fact and m.fact not in seen:
                seen.add(m.fact)
                merged.append(m)
        return merged

    async def recall_shared(
        self,
        shared_channel: str,
        query: str,
        top_k: int = 10,
    ) -> list[Memory]:
        """Cross-user shared-channel recall.

        ADK's VertexAiMemoryBankService does not model shared channels,
        so we partition by app_name as `"<base>/shared/<channel>"` and
        use a placeholder user_id of "shared". This is a best-effort
        shim — callers should consider it a feature we don't fully
        support on the native backend yet.
        """
        app = f"{self._base_app_name}/shared/{shared_channel}"
        try:
            response = await self._native.search_memory(
                app_name=app,
                user_id="shared",
                query=query,
            )
        except Exception:
            logger.warning(
                "Native shared recall failed for %s", shared_channel, exc_info=True
            )
            return []
        return [self._entry_to_memory(e) for e in response.memories[:top_k]]

    async def capture(
        self,
        user_id: str,
        conversation_text: str,
        agent_id: str | None = None,
        topics: list[str] | None = None,
    ) -> list[Memory]:
        """Auto-capture: fire-and-forget extraction after each turn.

        Translates `conversation_text` into a list of ADK Events and
        calls `add_events_to_memory`. Errors are logged and suppressed.
        Returns an empty list — the native API doesn't surface the
        generated memories synchronously (it's a long-running
        operation).
        """
        app = self._scope_app_name(agent_id)
        events = self._parse_conversation_to_events(conversation_text)
        if not events:
            return []

        custom_metadata: dict[str, object] | None = None
        if topics:
            custom_metadata = {"topics": list(topics)}

        try:
            await self._native.add_events_to_memory(
                app_name=app,
                user_id=user_id,
                events=events,
                custom_metadata=custom_metadata,
            )
        except Exception:
            logger.warning(
                "Native capture failed for %s (agent=%s)",
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
        """End-of-session memory extraction. Raises on error — callers
        (SessionService.end_session, AgentRunner.end_session) handle it."""
        app = self._scope_app_name(agent_id)
        events = self._parse_conversation_to_events(conversation_text)
        if not events:
            return []
        await self._native.add_events_to_memory(
            app_name=app,
            user_id=user_id,
            events=events,
        )
        return []

    def format_for_prompt(self, memories: list[Memory]) -> str:
        """Same signature as MemoryService.format_for_prompt.

        Delegates to the canonical formatter so both backends render
        identically — no drift between custom and native paths.
        """
        from gclaw.memory.service import MemoryService
        return MemoryService.format_for_prompt(self, memories)  # type: ignore[arg-type]

    def _entry_to_memory(self, entry: "_MemoryEntryLike") -> Memory:
        """Translate an ADK MemoryEntry into our Memory model.

        Structured fields (summary, entities, topics, importance)
        default — ADK's MemoryEntry doesn't carry them.
        """
        text = ""
        content = getattr(entry, "content", None)
        if content is not None:
            parts = getattr(content, "parts", None) or []
            for part in parts:
                part_text = getattr(part, "text", None)
                if part_text:
                    text = part_text
                    break
        return Memory(
            fact=text,
            update_time=getattr(entry, "timestamp", None),
        )

    def _parse_conversation_to_events(self, conversation_text: str) -> list:
        """Build ADK Event objects from a `User:/Agent:` formatted transcript.

        AgentRunner emits conversation_text as:
            User: <message>
            Agent: <response>

        Each line becomes one Event with a `types.Content` carrying the
        appropriate role. Empty lines are skipped.
        """
        from google.adk.events.event import Event
        from google.genai import types

        events: list[Event] = []
        for line in conversation_text.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("User:"):
                role = "user"
                text = line[len("User:"):].strip()
            elif line.startswith("Agent:"):
                role = "model"
                text = line[len("Agent:"):].strip()
            else:
                role = "user"
                text = line
            if not text:
                continue
            events.append(
                Event(
                    author=role,
                    invocation_id="",
                    content=types.Content(
                        role=role,
                        parts=[types.Part(text=text)],
                    ),
                )
            )
        return events


class _MemoryEntryLike:
    """Type alias marker for duck-typed MemoryEntry."""
    content: object
    timestamp: str | None
