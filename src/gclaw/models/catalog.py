"""Data models for the persistent model/provider catalog.

Providers and Models are stored in Firestore under
``config/catalog/providers/{id}`` and ``config/catalog/models/{id}``.
API keys may be stored inline (literal), via an env var name (env), or
a Secret Manager resource path (sm — placeholder for future).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


# --- API key -----------------------------------------------------------------


class ApiKeyKind(str, Enum):
    LITERAL = "literal"       # stored inline (Firestore encrypts at rest; IAM-gated)
    ENV = "env"               # value is env var NAME
    SECRET_MANAGER = "sm"     # value is SM resource path (placeholder for future)


class ApiKeySpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: ApiKeyKind
    value: str


# --- Provider ----------------------------------------------------------------


class ProviderKind(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE_GEMINI = "google_gemini"
    GOOGLE_VERTEX = "google_vertex"
    OPENROUTER = "openrouter"
    OLLAMA = "ollama"
    GROQ = "groq"
    TOGETHER = "together"
    CUSTOM_OPENAI = "custom_openai"  # OpenAI-compatible endpoint with custom base_url


class ModelProvider(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: f"prov_{uuid.uuid4().hex[:12]}")
    name: str
    kind: ProviderKind
    base_url: str | None = None
    api_key: ApiKeySpec | None = None
    default_headers: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_firestore_dict(self) -> dict:
        d = self.model_dump(mode="json")
        d.pop("id", None)
        return d

    @classmethod
    def from_firestore_dict(cls, doc_id: str, data: dict) -> "ModelProvider":
        data = dict(data)
        return cls(id=doc_id, **data)


# --- Model -------------------------------------------------------------------


class Capabilities(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: bool = True
    vision: bool = False
    tools: bool = False
    reasoning: bool = False
    streaming: bool = True


class ModelCost(BaseModel):
    model_config = ConfigDict(extra="ignore")

    input_per_mtok: float | None = None
    output_per_mtok: float | None = None
    cache_read_per_mtok: float | None = None
    cache_write_per_mtok: float | None = None


class ModelParams(BaseModel):
    model_config = ConfigDict(extra="ignore")

    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    thinking_budget: int | None = None
    extra: dict[str, object] = Field(default_factory=dict)


class ModelRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: f"mdl_{uuid.uuid4().hex[:12]}")
    provider_id: str
    model_id: str
    display_name: str
    enabled: bool = True
    context_window: int | None = None
    max_output_tokens: int | None = None
    capabilities: Capabilities = Field(default_factory=Capabilities)
    params: ModelParams = Field(default_factory=ModelParams)
    cost: ModelCost = Field(default_factory=ModelCost)
    notes: str = ""
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_firestore_dict(self) -> dict:
        d = self.model_dump(mode="json")
        d.pop("id", None)
        return d

    @classmethod
    def from_firestore_dict(cls, doc_id: str, data: dict) -> "ModelRecord":
        data = dict(data)
        return cls(id=doc_id, **data)


# --- Agent frontmatter model reference --------------------------------------


class AgentModelRef(BaseModel):
    """Reference to a catalog model from an agent's YAML frontmatter.

    ``name`` is either ``"ProviderName/model_id"`` or a bare ``"model_id"``
    (which will be resolved against all enabled providers). ``params``
    carries optional per-call overrides.
    """

    model_config = ConfigDict(extra="ignore")

    name: str
    params: ModelParams | None = None
