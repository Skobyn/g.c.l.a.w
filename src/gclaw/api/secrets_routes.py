"""Admin API routes for Secret Manager writes driven from the UI.

Mounted under ``/admin/secrets``. These endpoints are write-only for
values — no endpoint ever returns a secret value. The list endpoint only
returns names + metadata.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from gclaw.auth.dependencies import get_current_user_id
from gclaw.catalog.secret_manager import (
    SecretManagerNotFoundError,
    SecretManagerPermissionError,
    SecretManagerService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/secrets", tags=["secrets"])

_sm_service: SecretManagerService | None = None


# --- Request/response models ------------------------------------------------


class WriteSecretRequest(BaseModel):
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        pattern=r"^[a-z0-9][a-z0-9-]*$",
    )
    value: str = Field(..., min_length=1)
    create_if_missing: bool = True


class WriteSecretResponse(BaseModel):
    name: str
    path: str
    version_id: str
    created_secret: bool


class RotateSecretRequest(BaseModel):
    value: str = Field(..., min_length=1)


class RotateSecretResponse(BaseModel):
    name: str
    path: str
    version_id: str


class SMSecretSummary(BaseModel):
    name: str
    path: str
    latest_version_created_at: str | None = None


class ListSecretsResponse(BaseModel):
    secrets: list[SMSecretSummary]


# --- Helpers ----------------------------------------------------------------


def _require_service() -> SecretManagerService:
    if _sm_service is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Secret Manager service is not configured on this server. "
                "Provide GCP_PROJECT_ID and grant the runtime SA "
                "roles/secretmanager.admin."
            ),
        )
    return _sm_service


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, SecretManagerNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, SecretManagerPermissionError):
        return HTTPException(status_code=500, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    logger.exception("secret manager admin error")
    return HTTPException(
        status_code=500,
        detail=f"Secret Manager error: {exc}",
    )


# --- Router -----------------------------------------------------------------


def init_secrets_router(
    sm_service: SecretManagerService | None,
) -> APIRouter:
    """Install the provided service and return the router.

    Passing ``None`` still returns a router, but all endpoints will
    reply 503 so callers can mount it unconditionally and have a
    consistent URL space.
    """
    global _sm_service
    _sm_service = sm_service

    @router.post("", response_model=WriteSecretResponse)
    def write_secret(
        body: WriteSecretRequest,
        user_id: str = Depends(get_current_user_id),
    ) -> WriteSecretResponse:
        svc = _require_service()
        # Pre-validate name with the same normalization rule so we can
        # 409 cleanly when create_if_missing=False and the caller's
        # name doesn't resolve to an existing secret.
        try:
            result = svc.write(
                name=body.name,
                value=body.value,
                create_if_missing=body.create_if_missing,
            )
        except SecretManagerNotFoundError as e:
            # write() only raises NotFound when create_if_missing=False.
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Secret does not exist and create_if_missing=false: {e}"
                ),
            )
        except Exception as e:
            raise _map_error(e)
        return WriteSecretResponse(**result)

    @router.get("", response_model=ListSecretsResponse)
    def list_secrets(
        user_id: str = Depends(get_current_user_id),
    ) -> ListSecretsResponse:
        svc = _require_service()
        try:
            items = svc.list_gclaw_secrets()
        except Exception as e:
            raise _map_error(e)
        return ListSecretsResponse(
            secrets=[SMSecretSummary(**item) for item in items]
        )

    @router.post("/{name}/rotate", response_model=RotateSecretResponse)
    def rotate_secret(
        name: str,
        body: RotateSecretRequest,
        user_id: str = Depends(get_current_user_id),
    ) -> RotateSecretResponse:
        svc = _require_service()
        try:
            result = svc.rotate(name=name, value=body.value)
        except Exception as e:
            raise _map_error(e)
        return RotateSecretResponse(
            name=result["name"],
            path=result["path"],
            version_id=result["version_id"],
        )

    return router
