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
    """A model endpoint — Gemini API, Vertex, or OpenAI-compatible via LiteLlm."""

    name: str
    endpoint_id: str
    provider: str = "gemini"
    max_context_tokens: int = 0


class RoutingRule(BaseModel):
    """Maps a task profile to a model name."""

    task_profile: TaskProfile
    model_name: str
