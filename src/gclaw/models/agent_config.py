"""Agent configuration override models.

Repo ``agents/*.md`` files remain the shipped baseline. User edits are
stored as Firestore ``AgentOverride`` docs that merge on top at load
time. Deleting an override reverts the agent to its baseline. Newly
created agents are override-only (``is_standalone=True``) and have no
baseline file.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from gclaw.heartbeat.config import HeartbeatConfig


class ThinkingLevel(str, Enum):
    OFF = "off"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    ADAPTIVE = "adaptive"


class AgentIdentity(BaseModel):
    model_config = ConfigDict(extra="ignore")

    display_name: str | None = None
    emoji: str | None = None
    avatar_url: str | None = None
    description: str | None = None


class AgentModelSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # primary may be a catalog ref "Provider/model_id" or bare model_id
    primary: str | None = None
    fallbacks: list[str] = Field(default_factory=list)
    thinking: ThinkingLevel | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class AgentToolsSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # profile = coarse preset; allow/deny = fine overrides on top of profile
    profile: str | None = None  # "default" | "minimal" | "coding" | "messaging" | "full"
    allow: list[str] = Field(default_factory=list)
    deny: list[str] = Field(default_factory=list)
    # Catalog tool IDs (from /admin/tools). The factory resolves each to
    # its underlying callable via ToolBindingService and appends the
    # result to the agent's tool list. Legacy allow/deny still apply
    # on top of the merged result.
    catalog_tool_ids: list[str] = Field(default_factory=list)


class AgentSubagentsSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # None = inherit hierarchy default; list = explicit allowlist;
    # ["*"] = any agent can be delegated to.
    allow: list[str] | None = None


class AgentOverride(BaseModel):
    """Firestore-backed user overrides layered atop a file-backed agent."""

    model_config = ConfigDict(extra="ignore")

    agent_name: str  # doc id
    identity: AgentIdentity = Field(default_factory=AgentIdentity)
    model: AgentModelSpec = Field(default_factory=AgentModelSpec)
    tools: AgentToolsSpec = Field(default_factory=AgentToolsSpec)
    subagents: AgentSubagentsSpec = Field(default_factory=AgentSubagentsSpec)
    skills: list[str] | None = None  # None = inherit; list = allowlist
    heartbeat: HeartbeatConfig | None = None  # None = inherit from .md or off
    # Whether this agent receives the shared user.md profile in its
    # system prompt. ``None`` = inherit (frontmatter, else per-agent
    # default — on for the orchestrator, off for everyone else).
    user_knowledge: bool | None = None
    system_prompt_override: str | None = None
    body_override: str | None = None
    soul_overlay: str | None = None  # full soul overlay markdown
    enabled: bool = True
    is_standalone: bool = False
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_firestore_dict(self) -> dict:
        d = self.model_dump(mode="json")
        d.pop("agent_name", None)
        return d

    @classmethod
    def from_firestore_dict(cls, doc_id: str, data: dict) -> "AgentOverride":
        data = dict(data)
        data.pop("agent_name", None)
        # Back-compat: allow legacy flat dicts with just `body` or
        # `system_prompt` fields.
        if "body" in data and "body_override" not in data:
            data["body_override"] = data.pop("body")
        if "system_prompt" in data and "system_prompt_override" not in data:
            data["system_prompt_override"] = data.pop("system_prompt")
        return cls(agent_name=doc_id, **data)
