"""Data models for the Tool Catalog.

Tool records are stored in Firestore under ``config/tools/{id}``. Each
record's ``config`` is a pydantic discriminated union keyed on the
embedded ``kind`` literal — the top-level ``ToolRecord.kind`` is derived
from ``config.kind`` for query convenience without drift risk.

Auth shapes (AuthSpec) reference credentials by Secret Manager path —
the catalog itself never stores secret material. Callers (the HTTP-API
kind runtime, the MCP env-var injector) read the SM value at tool-call
time via the project's SecretManagerService.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ToolKind(str, Enum):
    BUILTIN = "builtin"
    MCP = "mcp"
    HTTP_API = "http_api"
    CODE_EXEC = "code_exec"


# --- Auth specs (used by HttpApiConfig) ------------------------------------


class ApiKeyAuth(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: Literal["api_key"] = "api_key"
    location: Literal["header", "query"]
    param_name: str
    credential_ref: str  # SM resource path holding the key value


class BearerAuth(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: Literal["bearer"] = "bearer"
    credential_ref: str  # SM resource path holding the bearer token


class BasicAuth(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: Literal["basic"] = "basic"
    credential_ref: str  # SM path: stores "user:pass" or a JSON blob


class OAuth2BearerAuth(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: Literal["oauth2"] = "oauth2"
    credential_ref: str  # SM path: access token (possibly via OAuthTokenManager)


class NoAuth(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: Literal["none"] = "none"


AuthSpec = Annotated[
    Union[ApiKeyAuth, BearerAuth, BasicAuth, OAuth2BearerAuth, NoAuth],
    Field(discriminator="kind"),
]


# --- Per-kind config variants ---------------------------------------------


class BuiltinConfig(BaseModel):
    """Reference to a function in src/gclaw/tools/*.py.

    ``function_path`` is a dotted import path (e.g.
    ``gclaw.tools.research_tools.web_search``). Resolution happens
    lazily at binding time; validation failures there surface as a
    disabled tool rather than a crash.
    """

    model_config = ConfigDict(extra="ignore")

    kind: Literal["builtin"] = "builtin"
    function_path: str


class McpConfig(BaseModel):
    """External Model Context Protocol server.

    ``allowed_tools=None`` exposes every tool the server advertises;
    a list restricts to exactly those names. Env vars are injected into
    the MCP subprocess (for stdio transport) or request headers (for
    sse/http) — credential substitution happens at connect time.
    """

    model_config = ConfigDict(extra="ignore")

    kind: Literal["mcp"] = "mcp"
    transport: Literal["stdio", "sse", "http"]
    endpoint: str
    allowed_tools: list[str] | None = None
    env: dict[str, str] = Field(default_factory=dict)


class HttpApiConfig(BaseModel):
    """OpenAPI-described HTTP API, auto-wrapped as an in-process MCP.

    Exactly one of ``spec_url`` or ``spec_inline`` must be provided.
    ``allowed_operations`` whitelists operation IDs (None = all).
    """

    model_config = ConfigDict(extra="ignore")

    kind: Literal["http_api"] = "http_api"
    spec_url: str | None = None
    spec_inline: dict | None = None
    base_url: str
    auth: AuthSpec
    allowed_operations: list[str] | None = None

    @model_validator(mode="after")
    def _require_one_spec(self):
        if self.spec_url is None and self.spec_inline is None:
            raise ValueError(
                "HttpApiConfig requires either spec_url or spec_inline"
            )
        return self


class CodeExecConfig(BaseModel):
    """Sandboxed code runner. Enforcement lives in the runner layer;
    this record captures policy intent only."""

    model_config = ConfigDict(extra="ignore")

    kind: Literal["code_exec"] = "code_exec"
    runtime: Literal["python3.12", "bash"]
    timeout_seconds: int = 30
    memory_mb: int = 256
    network: Literal["none", "egress-only"] = "none"
    allowed_modules: list[str] = Field(default_factory=list)


ToolConfig = Annotated[
    Union[BuiltinConfig, McpConfig, HttpApiConfig, CodeExecConfig],
    Field(discriminator="kind"),
]


# --- Top-level record -----------------------------------------------------


class ToolRecord(BaseModel):
    """A single catalog entry."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: f"tool_{uuid.uuid4().hex[:12]}")
    name: str
    enabled: bool = True
    config: ToolConfig
    credential_ref: str | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def kind(self) -> ToolKind:
        """Derived from ``config.kind`` — single source of truth."""
        return ToolKind(self.config.kind)

    def to_firestore_dict(self) -> dict:
        d = self.model_dump(mode="json")
        d.pop("id", None)
        return d

    @classmethod
    def from_firestore_dict(cls, doc_id: str, data: dict) -> "ToolRecord":
        data = dict(data)
        return cls(id=doc_id, **data)
