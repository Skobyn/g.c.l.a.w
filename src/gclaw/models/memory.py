"""Memory models for Vertex AI Memory Bank integration."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class MemoryTopic(str, Enum):
    """Memory topics — both Google-managed and custom."""

    # Google managed
    USER_PREFERENCES = "USER_PREFERENCES"
    EXPLICIT_INSTRUCTIONS = "EXPLICIT_INSTRUCTIONS"
    KEY_CONVERSATION_DETAILS = "KEY_CONVERSATION_DETAILS"

    # Custom topics
    PROJECT_CONTEXT = "project_context"
    ACTION_ITEMS = "action_items"
    RELATIONSHIPS = "relationships"
    ROUTINES = "routines"
    DOMAIN_KNOWLEDGE = "domain_knowledge"


class MemoryScope(BaseModel):
    """Scope for memory operations.

    - user_id only: user-scoped (shared across all agents)
    - user_id + agent: agent-scoped (domain-specific per agent)
    - shared_channel: cross-user shared scope (consent-based)
    """

    user_id: str
    agent: str | None = None
    shared_channel: str | None = None


class Memory(BaseModel):
    """A single memory fact from the Memory Bank.

    The schema borrows the always-on-memory-agent reference shape:
    `fact` remains the primary text payload, `summary` is a short
    headline for dense recall displays, `entities` and `topics` are
    lists for indexed retrieval, and `importance` (0.0-1.0) lets
    consolidation rank memories for retention.
    """

    fact: str
    summary: str = ""
    entities: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    importance: float = 0.5
    update_time: str | None = None
    score: float | None = None  # relevance score from retrieve

    @model_validator(mode="before")
    @classmethod
    def _accept_singular_topic(cls, data: Any) -> Any:
        """Accept the old `topic="..."` kwarg and promote it to `topics`.

        The schema moved from a single `topic: str` to `topics: list[str]`.
        Rather than rewrite every test fixture and every Firestore record,
        we translate the legacy shape on input: if `topic` is present and
        `topics` is not, wrap the singular value in a one-element list.
        """
        if isinstance(data, dict) and "topic" in data and "topics" not in data:
            data = dict(data)
            legacy = data.pop("topic")
            if legacy:
                data["topics"] = [legacy]
        return data

    @property
    def topic(self) -> str:
        """Back-compat shim: primary topic as a single string.

        The schema moved from a single `topic: str` field to
        `topics: list[str]`. Callers that read `.topic` get the
        first topic (or the empty string) without breaking.
        """
        return self.topics[0] if self.topics else ""
