"""Session service — business logic for conversation session management."""

from __future__ import annotations

from typing import TYPE_CHECKING

from gclaw.firestore.session_repo import SessionRepo
from gclaw.models.session import (
    MessageRole,
    Session,
    SessionMessage,
    SessionStatus,
)

if TYPE_CHECKING:
    from gclaw.memory.service import MemoryService


class SessionService:
    """High-level operations on conversation sessions."""

    def __init__(
        self,
        session_repo: SessionRepo,
        memory_service: MemoryService | None = None,
        compaction_threshold: int = 50,
    ) -> None:
        self._repo = session_repo
        self._memory = memory_service
        self._compaction_threshold = compaction_threshold

    def create(
        self,
        user_id: str,
        agent_id: str | None = None,
        metadata: dict | None = None,
    ) -> Session:
        session = Session(
            user_id=user_id,
            agent_id=agent_id,
            metadata=metadata or {},
        )
        return self._repo.create(session)

    def create_with_id(
        self,
        session_id: str,
        user_id: str,
        agent_id: str | None = None,
        metadata: dict | None = None,
    ) -> Session:
        """Create a session with a caller-supplied id.

        Used by AgentRunner to mirror ADK session ids into the persistent
        store so the two session surfaces stay aligned.
        """
        session = Session(
            id=session_id,
            user_id=user_id,
            agent_id=agent_id,
            metadata=metadata or {},
        )
        return self._repo.create(session)

    def get_or_none(self, session_id: str) -> Session | None:
        """Return the session or None — does not raise on missing."""
        return self._repo.get(session_id)

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> Session:
        session = self._repo.get(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")

        msg = SessionMessage(role=MessageRole(role), content=content)
        updated = session.append_message(msg)
        return self._repo.update(updated)

    def get_history(
        self,
        session_id: str,
        limit: int | None = None,
    ) -> list[SessionMessage]:
        session = self._repo.get(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")

        if limit is not None:
            return session.get_recent_messages(limit=limit)
        return list(session.messages)

    def needs_compaction(self, session: Session) -> bool:
        """Check if a session needs mid-session compaction."""
        return session.message_count >= self._compaction_threshold

    def compact(
        self,
        session_id: str,
        summary: str,
        keep_recent: int = 10,
    ) -> Session:
        """Compact a session: store summary, keep only recent messages.

        This is mid-session compaction — the session stays active but
        older messages are replaced with a summary.
        """
        session = self._repo.get(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")

        recent = session.get_recent_messages(limit=keep_recent)
        compacted = session.model_copy(
            update={
                "messages": recent,
                "compaction_summary": summary,
            }
        )
        return self._repo.update(compacted)

    async def end_session(self, session_id: str) -> Session:
        """End a session and extract memories if memory service is available.

        This is end-of-session compaction:
        1. Send full history to Memory Bank's memories:generate
        2. Mark session as ended
        """
        session = self._repo.get(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")

        # Extract memories from conversation if memory service is available
        if self._memory is not None and session.messages:
            conversation_text = "\n".join(
                f"{m.role.value}: {m.content}" for m in session.messages
            )
            await self._memory.generate_memories(
                user_id=session.user_id,
                conversation_text=conversation_text,
            )

        ended = session.end()
        return self._repo.update(ended)
