"""Session model for conversation state management."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field
from typing_extensions import Self


class SessionStatus(str, Enum):
    ACTIVE = "active"
    ENDED = "ended"
    COMPACTED = "compacted"


class MessageRole(str, Enum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


class SessionMessage(BaseModel):
    """A single message in a session's history."""

    role: MessageRole
    content: str
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class Session(BaseModel):
    """A conversation session stored in Firestore.

    Contains the message history between the user and agents.
    Sessions can be compacted (summarized) when context fills up,
    with the summary stored and raw messages optionally retained.
    """

    id: str = Field(default_factory=lambda: f"sess_{uuid.uuid4().hex[:12]}")
    user_id: str
    agent_id: str | None = None
    status: SessionStatus = SessionStatus.ACTIVE
    messages: list[SessionMessage] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    compaction_summary: str | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def message_count(self) -> int:
        return len(self.messages)

    def append_message(self, message: SessionMessage) -> Self:
        """Return a copy with the message appended."""
        new_messages = list(self.messages) + [message]
        return self.model_copy(
            update={
                "messages": new_messages,
                "updated_at": datetime.now(timezone.utc),
            }
        )

    def get_recent_messages(self, limit: int = 20) -> list[SessionMessage]:
        """Get the most recent messages."""
        return self.messages[-limit:]

    def mark_compacted(self, summary: str) -> Self:
        """Mark the session as compacted with a summary."""
        return self.model_copy(
            update={
                "status": SessionStatus.COMPACTED,
                "compaction_summary": summary,
                "updated_at": datetime.now(timezone.utc),
            }
        )

    def end(self) -> Self:
        """Mark the session as ended."""
        return self.model_copy(
            update={
                "status": SessionStatus.ENDED,
                "updated_at": datetime.now(timezone.utc),
            }
        )

    def to_firestore_dict(self) -> dict:
        d = self.model_dump(mode="json")
        d.pop("id")
        return d

    @classmethod
    def from_firestore_dict(cls, doc_id: str, data: dict) -> Self:
        return cls(id=doc_id, **data)
