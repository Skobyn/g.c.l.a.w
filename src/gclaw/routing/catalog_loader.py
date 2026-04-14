"""Build a ModelRouter from a persisted CatalogService."""

from __future__ import annotations

import logging

from gclaw.catalog.adk_builder import build_adk_override_from_model
from gclaw.catalog.service import CatalogService
from gclaw.models.catalog import ModelProvider, ModelRecord, ProviderKind
from gclaw.models.model_config import ModelEndpoint
from gclaw.routing.router import ModelRouter

logger = logging.getLogger(__name__)


def _endpoint_name(provider: ModelProvider, model: ModelRecord) -> str:
    return f"{provider.name}/{model.model_id}"


def _provider_tag(kind: ProviderKind) -> str:
    # Map catalog kind → the `provider` string used by ModelEndpoint.
    if kind in (ProviderKind.GOOGLE_GEMINI,):
        return "gemini"
    if kind == ProviderKind.GOOGLE_VERTEX:
        return "vertex"
    return kind.value


def load_endpoints_from_catalog(
    catalog_service: CatalogService,
    fallback_flash_model: str,
) -> ModelRouter:
    """Build a ModelRouter from the persisted catalog.

    Every enabled model becomes a named endpoint on the router. Non-Gemini
    providers are wrapped with LiteLlm carrying the provider's resolved
    api_key and base_url; Gemini/Vertex are registered as bare strings.
    Routing rules are left empty — profile-level resolution is kept in
    main.py for now (catalog just supplies the endpoints).
    """
    providers = {p.id: p for p in catalog_service.list_providers()}
    endpoints: dict[str, ModelEndpoint] = {}
    adk_overrides: dict[str, object] = {}

    for model in catalog_service.list_models():
        if not model.enabled:
            continue
        provider = providers.get(model.provider_id)
        if provider is None or not provider.enabled:
            continue

        name = _endpoint_name(provider, model)
        endpoints[name] = ModelEndpoint(
            name=name,
            endpoint_id=model.model_id,
            provider=_provider_tag(provider.kind),
            max_context_tokens=model.context_window or 128_000,
        )
        api_key = catalog_service.resolve_api_key(provider)
        adk_overrides[name] = build_adk_override_from_model(provider, model, api_key)

    router = ModelRouter(
        endpoints=endpoints,
        rules=[],
        default_model=fallback_flash_model,
    )
    for name, obj in adk_overrides.items():
        router.register_adk_override(name, obj)
    return router
