"""Data models for multi-model routing configuration."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class TaskProfile(str, Enum):
    """Task profiles that determine which model tier to use."""

    ORCHESTRATION = "orchestration"
    TOOL_EXECUTION = "tool_execution"
    CODE_GENERATION = "code_generation"
    SUMMARIZATION = "summarization"
    PERSONALITY = "personality"
    BACKGROUND = "background"


class ModelEndpoint(BaseModel):
    """A model endpoint deployed on Vertex AI or accessible via NIM."""

    name: str
    endpoint_id: str
    provider: str = "gemini"
    api_base: str | None = None
    api_key_env: str | None = None
    max_context_tokens: int = 0

    @property
    def is_remote(self) -> bool:
        return self.provider not in ("gemini", "vertex")


class RoutingRule(BaseModel):
    """Maps a task profile to a model name."""

    task_profile: TaskProfile
    model_name: str
