"""Admin API routes for the model catalog (providers + models).

Mounted under ``/admin``. API keys are redacted on GET responses for
ApiKeyKind.LITERAL values; env/sm references are returned unchanged
(they're pointers, not secrets).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from gclaw.auth.dependencies import get_current_user_id
from gclaw.catalog.presets import PRESETS, list_presets
from gclaw.catalog.service import CatalogService
from gclaw.catalog.test_connection import test_connection
from gclaw.models.catalog import (
    ApiKeyKind,
    ApiKeySpec,
    Capabilities,
    ModelCost,
    ModelParams,
    ModelProvider,
    ModelRecord,
    ProviderKind,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin")

_catalog_service: CatalogService | None = None


def init_catalog_router(catalog_service: CatalogService) -> APIRouter:
    global _catalog_service
    _catalog_service = catalog_service
    return router


def _require_service() -> CatalogService:
    if _catalog_service is None:
        raise HTTPException(status_code=503, detail="Catalog service not configured")
    return _catalog_service


# --- Serialization helpers --------------------------------------------------


def _serialize_provider(p: ModelProvider, *, model_count: int | None = None) -> dict:
    d = p.model_dump(mode="json")
    # Redact literal API keys
    if p.api_key is not None and p.api_key.kind == ApiKeyKind.LITERAL:
        d["api_key"] = {"kind": p.api_key.kind.value, "value": "***"}
    if model_count is not None:
        d["model_count"] = model_count
    return d


def _serialize_model(m: ModelRecord) -> dict:
    return m.model_dump(mode="json")


# --- Request bodies ---------------------------------------------------------


class ProviderCreateRequest(BaseModel):
    name: str
    kind: ProviderKind
    base_url: str | None = None
    api_key: ApiKeySpec | None = None
    default_headers: dict[str, str] = {}
    enabled: bool = True


class ProviderUpdateRequest(BaseModel):
    name: str | None = None
    kind: ProviderKind | None = None
    base_url: str | None = None
    api_key: ApiKeySpec | None = None
    default_headers: dict[str, str] | None = None
    enabled: bool | None = None


class ModelCreateRequest(BaseModel):
    provider_id: str
    model_id: str
    display_name: str
    enabled: bool = True
    context_window: int | None = None
    max_output_tokens: int | None = None
    capabilities: Capabilities | None = None
    params: ModelParams | None = None
    cost: ModelCost | None = None
    notes: str = ""


class ModelUpdateRequest(BaseModel):
    model_id: str | None = None
    display_name: str | None = None
    enabled: bool | None = None
    context_window: int | None = None
    max_output_tokens: int | None = None
    capabilities: Capabilities | None = None
    params: ModelParams | None = None
    cost: ModelCost | None = None
    notes: str | None = None


class InstallPresetsRequest(BaseModel):
    model_ids: list[str]


# --- Providers --------------------------------------------------------------


@router.get("/model-providers")
def list_providers(user_id: str = Depends(get_current_user_id)):
    svc = _require_service()
    providers = svc.list_providers()
    # Bulk count models per provider to avoid N queries
    all_models = svc.list_models()
    counts: dict[str, int] = {}
    for m in all_models:
        counts[m.provider_id] = counts.get(m.provider_id, 0) + 1
    return [
        _serialize_provider(p, model_count=counts.get(p.id, 0))
        for p in providers
    ]


@router.post("/model-providers")
def create_provider(
    req: ProviderCreateRequest,
    user_id: str = Depends(get_current_user_id),
):
    svc = _require_service()
    provider = svc.create_provider(**req.model_dump())
    return _serialize_provider(provider, model_count=0)


@router.get("/model-providers/{provider_id}")
def get_provider(
    provider_id: str,
    user_id: str = Depends(get_current_user_id),
):
    svc = _require_service()
    p = svc.get_provider(provider_id)
    if p is None:
        raise HTTPException(status_code=404, detail=f"Provider {provider_id!r} not found")
    count = len(svc.list_models(provider_id=provider_id))
    return _serialize_provider(p, model_count=count)


@router.patch("/model-providers/{provider_id}")
def update_provider(
    provider_id: str,
    req: ProviderUpdateRequest,
    user_id: str = Depends(get_current_user_id),
):
    svc = _require_service()
    updates: dict[str, Any] = {
        k: v for k, v in req.model_dump(exclude_unset=True).items() if v is not None
    }
    # api_key=None is a valid "clear the key" request; carry it through if
    # explicitly set
    if "api_key" in req.model_fields_set:
        updates["api_key"] = req.api_key
    try:
        provider = svc.update_provider(provider_id, **updates)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    count = len(svc.list_models(provider_id=provider_id))
    return _serialize_provider(provider, model_count=count)


@router.delete("/model-providers/{provider_id}")
def delete_provider(
    provider_id: str,
    user_id: str = Depends(get_current_user_id),
):
    svc = _require_service()
    if svc.get_provider(provider_id) is None:
        raise HTTPException(status_code=404, detail=f"Provider {provider_id!r} not found")
    svc.delete_provider(provider_id)
    return {"status": "deleted", "id": provider_id}


# --- Models -----------------------------------------------------------------


@router.get("/models")
def list_models(
    provider_id: str | None = None,
    user_id: str = Depends(get_current_user_id),
):
    svc = _require_service()
    return [_serialize_model(m) for m in svc.list_models(provider_id=provider_id)]


@router.post("/models")
def create_model(
    req: ModelCreateRequest,
    user_id: str = Depends(get_current_user_id),
):
    svc = _require_service()
    try:
        model = svc.create_model(**req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _serialize_model(model)


@router.get("/models/{model_id}")
def get_model(
    model_id: str,
    user_id: str = Depends(get_current_user_id),
):
    svc = _require_service()
    m = svc.get_model(model_id)
    if m is None:
        raise HTTPException(status_code=404, detail=f"Model {model_id!r} not found")
    return _serialize_model(m)


@router.patch("/models/{model_id}")
def update_model(
    model_id: str,
    req: ModelUpdateRequest,
    user_id: str = Depends(get_current_user_id),
):
    svc = _require_service()
    updates = {
        k: v for k, v in req.model_dump(exclude_unset=True).items() if v is not None
    }
    try:
        model = svc.update_model(model_id, **updates)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _serialize_model(model)


@router.delete("/models/{model_id}")
def delete_model(
    model_id: str,
    user_id: str = Depends(get_current_user_id),
):
    svc = _require_service()
    if svc.get_model(model_id) is None:
        raise HTTPException(status_code=404, detail=f"Model {model_id!r} not found")
    svc.delete_model(model_id)
    return {"status": "deleted", "id": model_id}


@router.post("/models/{model_id}/test")
async def test_model(
    model_id: str,
    user_id: str = Depends(get_current_user_id),
):
    svc = _require_service()
    model = svc.get_model(model_id)
    if model is None:
        raise HTTPException(status_code=404, detail=f"Model {model_id!r} not found")
    provider = svc.get_provider(model.provider_id)
    if provider is None:
        raise HTTPException(
            status_code=400,
            detail=f"Provider {model.provider_id!r} not found for model {model_id!r}",
        )
    return await test_connection(provider, model)


# --- Presets ----------------------------------------------------------------


@router.get("/model-presets")
def get_presets(user_id: str = Depends(get_current_user_id)):
    return list_presets()


@router.post("/model-providers/{provider_id}/install-presets")
def install_presets(
    provider_id: str,
    req: InstallPresetsRequest,
    user_id: str = Depends(get_current_user_id),
):
    svc = _require_service()
    provider = svc.get_provider(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail=f"Provider {provider_id!r} not found")

    entry = PRESETS.get(provider.kind)
    if entry is None:
        raise HTTPException(
            status_code=400,
            detail=f"No presets available for provider kind {provider.kind.value!r}",
        )
    preset_models = {m["model_id"]: m for m in entry["models"]}

    created: list[dict] = []
    skipped: list[str] = []
    for model_id in req.model_ids:
        preset = preset_models.get(model_id)
        if preset is None:
            skipped.append(model_id)
            continue
        kwargs = dict(preset)
        caps = kwargs.pop("capabilities", None)
        created_model = svc.create_model(
            provider_id=provider_id,
            model_id=kwargs.pop("model_id"),
            display_name=kwargs.pop("display_name"),
            context_window=kwargs.pop("context_window", None),
            max_output_tokens=kwargs.pop("max_output_tokens", None),
            capabilities=Capabilities(**caps) if caps else None,
        )
        created.append(_serialize_model(created_model))
    return {"created": created, "skipped": skipped}
