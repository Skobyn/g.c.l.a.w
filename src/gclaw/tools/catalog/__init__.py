"""Tool Catalog — persistent, configurable tool registry.

Public surface:
    - models.*          Pydantic types (ToolRecord, ToolKind, configs, AuthSpec variants)
    - service.*         ToolCatalogService (CRUD orchestration)
    - (firestore.tool_repo.ToolRepo is the storage layer; not re-exported
       here because callers construct it directly with a Firestore client)

Loaded lazily from ``gclaw.main`` at boot; mirrors the shape of the
existing ModelCatalog (providers/models) so agents treat them the same way.
"""

from __future__ import annotations

from gclaw.tools.catalog.models import (  # noqa: F401
    ApiKeyAuth,
    AuthSpec,
    BasicAuth,
    BearerAuth,
    BuiltinConfig,
    CodeExecConfig,
    HttpApiConfig,
    McpConfig,
    NoAuth,
    OAuth2BearerAuth,
    ToolConfig,
    ToolKind,
    ToolRecord,
)
from gclaw.tools.catalog.service import ToolCatalogService  # noqa: F401
