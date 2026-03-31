"""Memory models for Vertex AI Memory Bank integration."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


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
    """

    user_id: str
    agent: str | None = None


class Memory(BaseModel):
    """A single memory fact from the Memory Bank."""

    fact: str
    topic: str = ""
    update_time: str | None = None
    score: float | None = None  # relevance score from retrieve
