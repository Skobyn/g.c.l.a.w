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
_oauth_manager: object | None = None


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


class OAuthSecretRequest(BaseModel):
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        pattern=r"^[a-z0-9][a-z0-9-]*$",
    )
    access_token: str = Field(..., min_length=1)
    refresh_token: str = Field(..., min_length=1)
    # Optional — if the user knows it. Defaults to 8h to match Claude Code
    # tokens' typical lifetime.
    expires_in_seconds: int | None = Field(default=None, ge=60)


class OAuthRefreshResponse(BaseModel):
    refreshed: bool
    expires_at: str | None = None


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
    oauth_manager: object | None = None,
) -> APIRouter:
    """Install the provided service and return the router.

    Passing ``None`` still returns a router, but all endpoints will
    reply 503 so callers can mount it unconditionally and have a
    consistent URL space.
    """
    global _sm_service, _oauth_manager
    _sm_service = sm_service
    _oauth_manager = oauth_manager

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

    @router.post("/oauth", response_model=WriteSecretResponse)
    async def write_oauth_secret(
        body: OAuthSecretRequest,
        user_id: str = Depends(get_current_user_id),
    ) -> WriteSecretResponse:
        """Bundle access + refresh tokens into a JSON blob and write to SM.

        The bundle schema is consumed by CatalogService.resolve_api_key for
        ANTHROPIC_OAUTH providers, and by OAuthTokenManager for the
        background refresh loop.
        """
        svc = _require_service()
        from datetime import datetime, timedelta, timezone

        from gclaw.catalog.oauth_tokens import (
            DEFAULT_EXPIRES_IN_SECONDS,
            OAuthTokenBundle,
        )

        expires_in = body.expires_in_seconds or DEFAULT_EXPIRES_IN_SECONDS
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        bundle = OAuthTokenBundle(
            access_token=body.access_token,
            refresh_token=body.refresh_token,
            expires_at=expires_at,
        )
        try:
            result = svc.write(
                name=body.name,
                value=bundle.to_json(),
                create_if_missing=True,
            )
        except Exception as e:
            raise _map_error(e)
        # Opportunistically register the new secret with the refresh loop.
        if _oauth_manager is not None:
            try:
                await _oauth_manager.register(result["path"])  # type: ignore[attr-defined]
            except Exception:
                logger.warning(
                    "oauth-register: failed to register new secret with manager",
                    exc_info=True,
                )
        return WriteSecretResponse(**result)

    @router.post("/oauth/{name}/refresh-now", response_model=OAuthRefreshResponse)
    async def refresh_oauth_secret_now(
        name: str,
        user_id: str = Depends(get_current_user_id),
    ) -> OAuthRefreshResponse:
        """Force an immediate refresh of the named OAuth secret.

        Useful for debugging from the UI. 404 if the secret doesn't exist
        or doesn't contain a refresh_token. 503 if no oauth_manager wired.
        """
        svc = _require_service()
        if _oauth_manager is None:
            raise HTTPException(
                status_code=503,
                detail="OAuth token manager not configured on this server.",
            )
        norm = svc.normalize_name(name)
        sm_path = f"projects/{svc.project}/secrets/{norm}/versions/latest"
        try:
            new_bundle = await _oauth_manager.refresh_now(sm_path)  # type: ignore[attr-defined]
        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail=f"OAuth refresh failed: {e}",
            )
        if new_bundle is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Secret {norm!r} has no refresh_token or isn't an "
                    "OAuth bundle."
                ),
            )
        return OAuthRefreshResponse(
            refreshed=True,
            expires_at=new_bundle.expires_at.isoformat(),
        )

    return router
