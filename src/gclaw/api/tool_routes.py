"""Admin API routes for the Tool Catalog.

Mounted under ``/admin``. Mirrors the shape of catalog_routes.py
(providers/models) so the web UI has one mental model across catalogs.
Credential material is never returned; ``credential_ref`` (an SM path)
flows through unchanged because it's a pointer, not a secret.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError

from gclaw.auth.dependencies import get_current_user_id
from gclaw.tools.catalog.models import ToolRecord
from gclaw.tools.catalog.service import ToolCatalogService
from gclaw.tools.catalog.tester import probe_tool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin")

_service: ToolCatalogService | None = None


def init_tool_router(service: ToolCatalogService) -> APIRouter:
    global _service
    _service = service
    return router


def _require_service() -> ToolCatalogService:
    if _service is None:
        raise HTTPException(
            status_code=503, detail="Tool catalog service not configured"
        )
    return _service


def _serialize(record: ToolRecord) -> dict:
    d = record.model_dump(mode="json")
    # Ensure the derived top-level kind is on the wire for the UI.
    d["kind"] = record.kind.value
    return d


# --- Request bodies ------------------------------------------------------


class ToolCreateRequest(BaseModel):
    name: str
    config: dict
    enabled: bool = True
    credential_ref: str | None = None


class ToolUpdateRequest(BaseModel):
    name: str | None = None
    config: dict | None = None
    enabled: bool | None = None
    credential_ref: str | None = None


# --- Routes --------------------------------------------------------------


@router.get("/tools")
def list_tools(user_id: str = Depends(get_current_user_id)):
    svc = _require_service()
    return [_serialize(t) for t in svc.list_tools()]


@router.post("/tools")
def create_tool(
    req: ToolCreateRequest,
    user_id: str = Depends(get_current_user_id),
):
    svc = _require_service()
    try:
        record = svc.create_tool(
            name=req.name,
            config=req.config,
            enabled=req.enabled,
            credential_ref=req.credential_ref,
        )
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=f"invalid config: {e.errors()}") from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _serialize(record)


@router.get("/tools/{tool_id}")
def get_tool(tool_id: str, user_id: str = Depends(get_current_user_id)):
    svc = _require_service()
    record = svc.get_tool(tool_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"tool {tool_id!r} not found")
    return _serialize(record)


@router.patch("/tools/{tool_id}")
def update_tool(
    tool_id: str,
    req: ToolUpdateRequest,
    user_id: str = Depends(get_current_user_id),
):
    svc = _require_service()
    updates: dict[str, Any] = req.model_dump(exclude_unset=True)
    try:
        record = svc.update_tool(tool_id, **updates)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=f"invalid config: {e.errors()}") from e
    return _serialize(record)


@router.delete("/tools/{tool_id}", status_code=204)
def delete_tool(tool_id: str, user_id: str = Depends(get_current_user_id)):
    svc = _require_service()
    svc.delete_tool(tool_id)
    return None


@router.post("/tools/{tool_id}/test")
async def test_tool_endpoint(
    tool_id: str, user_id: str = Depends(get_current_user_id)
):
    svc = _require_service()
    record = svc.get_tool(tool_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"tool {tool_id!r} not found")
    return await probe_tool(record)
