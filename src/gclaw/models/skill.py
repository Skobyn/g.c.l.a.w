"""Skill model for the capability layer."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field
from typing_extensions import Self


class TriggerMode(str, Enum):
    AUTO = "auto"
    MANUAL = "manual"
    BOTH = "both"


class SkillSource(str, Enum):
    BUILTIN = "builtin"
    IMPORTED = "imported"
    CUSTOM = "custom"


class SkillTrigger(BaseModel):
    """How and when a skill is invoked."""

    mode: TriggerMode = TriggerMode.MANUAL
    contexts: list[str] = Field(default_factory=list)
    command: str | None = None


class Skill(BaseModel):
    """A skill definition — a modular, composable capability.

    Skills are compound workflows with judgment, not just atomic API calls.
    They include instructions, examples, config, and tool orchestration.
    """

    name: str
    description: str
    version: str = "1.0.0"
    trigger: SkillTrigger = Field(default_factory=SkillTrigger)
    config: dict = Field(default_factory=dict)
    tools_required: list[str] = Field(default_factory=list)
    agents_granted: list[str] = Field(default_factory=list)
    source: SkillSource = SkillSource.BUILTIN
    instructions_path: str | None = None
    examples_path: str | None = None

    def is_granted_to(self, agent_name: str) -> bool:
        """Check if this skill is granted to the given agent."""
        return agent_name in self.agents_granted

    def matches_context(self, context: str) -> bool:
        """Check if the given context matches any of this skill's trigger contexts."""
        context_lower = context.lower()
        for trigger_ctx in self.trigger.contexts:
            if context_lower in trigger_ctx.lower() or trigger_ctx.lower() in context_lower:
                return True
        return False

    def to_firestore_dict(self) -> dict:
        return self.model_dump(mode="json")

    @classmethod
    def from_firestore_dict(cls, data: dict) -> Self:
        return cls(**data)
