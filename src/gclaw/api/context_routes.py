"""Admin API routes for the shared-context blackboard."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from gclaw.auth.dependencies import get_current_user_id
from gclaw.models.context_entry import ContextEntry
from gclaw.shared_context.service import SharedContextService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin")

_service: SharedContextService | None = None


def init_context_router(service: SharedContextService) -> APIRouter:
    global _service
    _service = service
    return router


def _require() -> SharedContextService:
    if _service is None:
        raise HTTPException(
            status_code=503,
            detail="Shared context service not configured",
        )
    return _service


def _serialize(entry: ContextEntry) -> dict:
    return entry.model_dump(mode="json")


class ContextCreateRequest(BaseModel):
    namespace: str
    content: str
    metadata: dict | None = None


@router.get("/context/namespaces")
def list_namespaces(user_id: str = Depends(get_current_user_id)):
    svc = _require()
    return svc.list_namespaces()


@router.get("/context")
def list_entries(
    namespace: str,
    limit: int = 20,
    since: str | None = None,
    user_id: str = Depends(get_current_user_id),
):
    svc = _require()
    since_dt: datetime | None = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
        except ValueError as e:
            raise HTTPException(
                status_code=400, detail=f"Invalid `since` timestamp: {e}"
            )
    entries = svc.list(namespace, limit=limit, since=since_dt)
    return [_serialize(e) for e in entries]


@router.get("/context/{entry_id}")
def get_entry(
    entry_id: str,
    user_id: str = Depends(get_current_user_id),
):
    svc = _require()
    entry = svc.get(entry_id)
    if entry is None:
        raise HTTPException(
            status_code=404, detail=f"Entry {entry_id!r} not found"
        )
    return _serialize(entry)


@router.get("/context/{entry_id}/blob")
def get_entry_blob(
    entry_id: str,
    user_id: str = Depends(get_current_user_id),
):
    svc = _require()
    entry = svc.get(entry_id)
    if entry is None:
        raise HTTPException(
            status_code=404, detail=f"Entry {entry_id!r} not found"
        )
    if not entry.blob_url:
        raise HTTPException(
            status_code=400,
            detail=f"Entry {entry_id!r} has no blob",
        )
    try:
        url = svc.signed_url_for(entry, minutes=15)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if url is None:
        raise HTTPException(
            status_code=503, detail="Blob store not configured"
        )
    return {"url": url, "expires_in_seconds": 900}


@router.delete("/context/{entry_id}")
def delete_entry(
    entry_id: str,
    user_id: str = Depends(get_current_user_id),
):
    svc = _require()
    entry = svc.get(entry_id)
    if entry is None:
        raise HTTPException(
            status_code=404, detail=f"Entry {entry_id!r} not found"
        )
    svc.delete(entry_id)
    return {"deleted": True, "id": entry_id}


@router.post("/context")
def create_entry(
    req: ContextCreateRequest,
    user_id: str = Depends(get_current_user_id),
):
    svc = _require()
    entry = svc.write_text(
        namespace=req.namespace,
        content=req.content,
        created_by=f"admin:{user_id}",
        metadata=req.metadata or {},
    )
    return _serialize(entry)
