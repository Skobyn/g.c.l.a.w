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
        oauth_manager: "object | None" = None,
        copilot_token_cache: "object | None" = None,
    ) -> None:
        self._providers = provider_repo
        self._models = model_repo
        self._sm_client = None
        # Optional OAuth manager for ANTHROPIC_OAUTH providers. When wired,
        # resolve_api_key uses it to mint a fresh access_token; otherwise we
        # fall back to a raw SM read + JSON parse.
        self._oauth_manager = oauth_manager
        # Optional cache that exchanges raw ``ghu_`` GitHub user tokens for
        # short-lived Copilot session tokens. When wired, resolve_api_key
        # routes Copilot-hosted providers through it.
        self._copilot_token_cache = copilot_token_cache

    def set_oauth_manager(self, oauth_manager) -> None:
        """Install an OAuth manager after construction (main.py wires this
        post-init because the manager needs the sm_service which is built
        alongside the catalog)."""
        self._oauth_manager = oauth_manager

    def set_copilot_token_cache(self, cache) -> None:
        """Install the Copilot token exchange cache post-construction."""
        self._copilot_token_cache = cache

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
            # Copilot branch: CUSTOM_OPENAI providers pointed at Copilot's
            # host store the raw ``ghu_`` GitHub user token in SM, which
            # Copilot rejects for most models (notably the codex family).
            # When a cache is wired, exchange it for a short-lived Copilot
            # session token before returning.
            if (
                provider.kind == ProviderKind.CUSTOM_OPENAI
                and "githubcopilot.com" in (provider.base_url or "").lower()
                and self._copilot_token_cache is not None
            ):
                try:
                    import asyncio
                    coro = self._copilot_token_cache.get_access_token(spec.value)
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            import concurrent.futures
                            with concurrent.futures.ThreadPoolExecutor(
                                max_workers=1
                            ) as ex:
                                fut = ex.submit(asyncio.run, coro)
                                token = fut.result(timeout=30)
                        else:
                            token = loop.run_until_complete(coro)
                    except RuntimeError:
                        token = asyncio.run(coro)
                    if token:
                        return token
                    # Fall through to raw SM read so the caller still gets
                    # something to attempt with — surfaces a clean 401.
                except Exception as e:
                    logger.warning(
                        "copilot-cache resolve failed for provider %s: %s",
                        provider.name,
                        e,
                    )

            # OAuth-aware branch: for ANTHROPIC_OAUTH providers, prefer the
            # token manager (auto-refreshes near-expiry tokens). Fall back
            # to raw SM read + JSON extract when no manager is wired (tests
            # and older deploys).
            if provider.kind == ProviderKind.ANTHROPIC_OAUTH:
                if self._oauth_manager is not None:
                    try:
                        import asyncio
                        # Sync callers (e.g. adk_builder at agent construction)
                        # need a blocking resolve. We run the coroutine on the
                        # current thread via asyncio.run when not already
                        # inside a loop; otherwise schedule + wait.
                        coro = self._oauth_manager.get_access_token(spec.value)
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                # Can't await in a sync context — fall back
                                # to a fresh loop in a worker thread.
                                import concurrent.futures
                                with concurrent.futures.ThreadPoolExecutor(
                                    max_workers=1
                                ) as ex:
                                    fut = ex.submit(asyncio.run, coro)
                                    return fut.result(timeout=30)
                            return loop.run_until_complete(coro)
                        except RuntimeError:
                            return asyncio.run(coro)
                    except Exception as e:
                        logger.warning(
                            "oauth-manager resolve failed for provider %s: %s",
                            provider.name,
                            e,
                        )
                        # Fall through to raw-read fallback.

                # Raw read + JSON parse (no manager wired)
                raw = self._raw_sm_read(spec.value, provider.name)
                if raw is None:
                    return None
                from gclaw.catalog.oauth_tokens import OAuthTokenBundle
                bundle = OAuthTokenBundle.parse(raw)
                if bundle is None:
                    return None
                return bundle.access_token

            return self._raw_sm_read(spec.value, provider.name)
        return None

    def _raw_sm_read(self, sm_path: str, provider_name: str) -> str | None:
        try:
            if self._sm_client is None:
                from google.cloud import secretmanager
                self._sm_client = secretmanager.SecretManagerServiceClient()
            resp = self._sm_client.access_secret_version(name=sm_path)
            return resp.payload.data.decode("utf-8")
        except Exception as e:
            logger.warning(
                "Secret Manager access failed for provider %s at %s: %s",
                provider_name,
                sm_path,
                e,
            )
            return None

    # --- Seeding --------------------------------------------------------

    def seed_system_defaults(self, *, settings) -> dict:
        """Idempotently upsert a 'System (Google)' provider reflecting the
        hardcoded Gemini endpoints the app falls back to when no other
        provider is configured. Users see what's actually running on the
        /admin/models page even before they add their own keys.

        Returns {created_providers, created_models} counts for logging.
        """
        provider_name = "System (Google)"
        existing = next(
            (p for p in self.list_providers() if p.name == provider_name),
            None,
        )
        if existing is None:
            provider = self.create_provider(
                name=provider_name,
                kind=ProviderKind.GOOGLE_GEMINI,
                base_url=None,
                api_key=None,  # uses ADC / Gemini API default
                default_headers={},
                enabled=True,
            )
            created_providers = 1
        else:
            provider = existing
            created_providers = 0

        # Models to reflect: whatever the hardcoded router wires today.
        defaults: list[dict] = []
        if settings.gemini_flash_model:
            defaults.append({
                "model_id": settings.gemini_flash_model,
                "display_name": f"Gemini Flash ({settings.gemini_flash_model})",
                "context_window": 1_000_000,
                "capabilities": Capabilities(vision=True, tools=True),
            })
        if getattr(settings, "gemma_endpoint_id", None):
            defaults.append({
                "model_id": settings.gemma_endpoint_id,
                "display_name": f"Gemma ({settings.gemma_endpoint_id})",
                "context_window": 128_000,
                "capabilities": Capabilities(),
            })
        if getattr(settings, "nemotron_endpoint_id", None):
            # Nemotron actually routes through OpenRouter; seed it under its
            # own provider for accuracy.
            pass

        existing_model_ids = {
            m.model_id for m in self.list_models(provider_id=provider.id)
        }
        created_models = 0
        for spec in defaults:
            if spec["model_id"] in existing_model_ids:
                continue
            self.create_model(
                provider_id=provider.id,
                model_id=spec["model_id"],
                display_name=spec["display_name"],
                enabled=True,
                context_window=spec.get("context_window"),
                max_output_tokens=None,
                capabilities=spec.get("capabilities", Capabilities()),
                params=ModelParams(),
                cost=ModelCost(),
                notes="Seeded default — reflects hardcoded router fallback.",
            )
            created_models += 1

        logger.info(
            "catalog seed: provider=%s created_providers=%d created_models=%d",
            provider_name,
            created_providers,
            created_models,
        )
        return {
            "created_providers": created_providers,
            "created_models": created_models,
        }
