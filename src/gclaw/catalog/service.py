"""CatalogService — thin orchestration over ProviderRepo/ModelRepo.

Handles cascading delete (removing a provider deletes its models) and
API key resolution (literal → value, env → os.environ lookup, sm →
placeholder until Secret Manager integration ships).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from gclaw.firestore.catalog_repo import ModelRepo, ProviderRepo
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


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CatalogService:
    def __init__(
        self,
        provider_repo: ProviderRepo,
        model_repo: ModelRepo,
    ) -> None:
        self._providers = provider_repo
        self._models = model_repo
        self._sm_client = None

    # --- Providers ------------------------------------------------------

    def create_provider(
        self,
        *,
        name: str,
        kind: ProviderKind,
        base_url: str | None = None,
        api_key: ApiKeySpec | None = None,
        default_headers: dict[str, str] | None = None,
        enabled: bool = True,
    ) -> ModelProvider:
        provider = ModelProvider(
            name=name,
            kind=kind,
            base_url=base_url,
            api_key=api_key,
            default_headers=default_headers or {},
            enabled=enabled,
        )
        return self._providers.create(provider)

    def get_provider(self, provider_id: str) -> ModelProvider | None:
        return self._providers.get(provider_id)

    def list_providers(self) -> list[ModelProvider]:
        return self._providers.list_all()

    def update_provider(self, provider_id: str, **updates) -> ModelProvider:
        current = self._providers.get(provider_id)
        if current is None:
            raise ValueError(f"Provider {provider_id!r} not found")
        payload = current.model_dump()
        # Strip keys we don't let callers mutate
        for field in ("id", "created_at"):
            updates.pop(field, None)
        payload.update(updates)
        payload["updated_at"] = _now()
        provider = ModelProvider(**payload)
        return self._providers.update(provider)

    def delete_provider(self, provider_id: str) -> None:
        # Cascade: remove all models for this provider first.
        for m in self._models.list_by_provider(provider_id):
            self._models.delete(m.id)
        self._providers.delete(provider_id)

    # --- Models ---------------------------------------------------------

    def create_model(
        self,
        *,
        provider_id: str,
        model_id: str,
        display_name: str,
        enabled: bool = True,
        context_window: int | None = None,
        max_output_tokens: int | None = None,
        capabilities: Capabilities | dict | None = None,
        params: ModelParams | dict | None = None,
        cost: ModelCost | dict | None = None,
        notes: str = "",
    ) -> ModelRecord:
        if self._providers.get(provider_id) is None:
            raise ValueError(f"Provider {provider_id!r} not found")

        if isinstance(capabilities, dict):
            capabilities = Capabilities(**capabilities)
        if isinstance(params, dict):
            params = ModelParams(**params)
        if isinstance(cost, dict):
            cost = ModelCost(**cost)

        model = ModelRecord(
            provider_id=provider_id,
            model_id=model_id,
            display_name=display_name,
            enabled=enabled,
            context_window=context_window,
            max_output_tokens=max_output_tokens,
            capabilities=capabilities or Capabilities(),
            params=params or ModelParams(),
            cost=cost or ModelCost(),
            notes=notes,
        )
        return self._models.create(model)

    def get_model(self, model_id: str) -> ModelRecord | None:
        return self._models.get(model_id)

    def list_models(self, provider_id: str | None = None) -> list[ModelRecord]:
        if provider_id is None:
            return self._models.list_all()
        return self._models.list_by_provider(provider_id)

    def update_model(self, model_id: str, **updates) -> ModelRecord:
        current = self._models.get(model_id)
        if current is None:
            raise ValueError(f"Model {model_id!r} not found")
        payload = current.model_dump()
        for field in ("id", "created_at", "provider_id"):
            updates.pop(field, None)
        # Normalize nested dicts
        for k in ("capabilities", "params", "cost"):
            if k in updates and isinstance(updates[k], dict):
                cls = {"capabilities": Capabilities, "params": ModelParams, "cost": ModelCost}[k]
                updates[k] = cls(**updates[k]).model_dump()
        payload.update(updates)
        payload["updated_at"] = _now()
        model = ModelRecord(**payload)
        return self._models.update(model)

    def delete_model(self, model_id: str) -> None:
        self._models.delete(model_id)

    # --- Key resolution -------------------------------------------------

    def resolve_api_key(self, provider: ModelProvider) -> str | None:
        spec = provider.api_key
        if spec is None:
            return None
        if spec.kind == ApiKeyKind.LITERAL:
            return spec.value
        if spec.kind == ApiKeyKind.ENV:
            value = os.environ.get(spec.value)
            if value is None:
                logger.warning(
                    "Provider %s references env var %s which is not set",
                    provider.name,
                    spec.value,
                )
            return value
        if spec.kind == ApiKeyKind.SECRET_MANAGER:
            try:
                if self._sm_client is None:
                    from google.cloud import secretmanager
                    self._sm_client = secretmanager.SecretManagerServiceClient()
                resp = self._sm_client.access_secret_version(name=spec.value)
                return resp.payload.data.decode("utf-8")
            except Exception as e:
                logger.warning(
                    "Secret Manager access failed for provider %s at %s: %s",
                    provider.name,
                    spec.value,
                    e,
                )
                return None
        return None
