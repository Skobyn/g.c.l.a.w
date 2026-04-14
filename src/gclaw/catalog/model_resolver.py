"""Resolve an ``AgentModelRef`` against a ``CatalogService``."""

from __future__ import annotations

import logging

from gclaw.catalog.service import CatalogService
from gclaw.models.catalog import AgentModelRef, ModelProvider, ModelRecord

logger = logging.getLogger(__name__)


def resolve_agent_model(
    ref: AgentModelRef,
    catalog: CatalogService,
) -> tuple[ModelProvider, ModelRecord] | None:
    """Resolve a frontmatter reference to ``(provider, model)``.

    Accepts ``"ProviderName/model_id"`` (split on first ``/``) or bare
    ``"model_id"``. Returns ``None`` if no match is found (with a warning
    logged). On ambiguity (bare id matches multiple enabled providers),
    returns the first match and warns.
    """
    name = ref.name.strip()
    if not name:
        return None

    providers = [p for p in catalog.list_providers() if p.enabled]
    provider_by_name = {p.name: p for p in providers}
    provider_by_id = {p.id: p for p in providers}

    if "/" in name:
        provider_name, _, model_id = name.partition("/")
        provider_name = provider_name.strip()
        model_id = model_id.strip()
        provider = provider_by_name.get(provider_name)
        if provider is None:
            logger.warning(
                "agent model ref %r: provider %r not found in catalog",
                name,
                provider_name,
            )
            return None
        for model in catalog.list_models(provider_id=provider.id):
            if model.enabled and model.model_id == model_id:
                return provider, model
        logger.warning(
            "agent model ref %r: model %r not found under provider %r",
            name,
            model_id,
            provider_name,
        )
        return None

    # Bare model_id — search across enabled providers.
    matches: list[tuple[ModelProvider, ModelRecord]] = []
    for model in catalog.list_models():
        if not model.enabled:
            continue
        if model.model_id != name:
            continue
        provider = provider_by_id.get(model.provider_id)
        if provider is None or not provider.enabled:
            continue
        matches.append((provider, model))

    if not matches:
        logger.warning(
            "agent model ref %r: no enabled catalog model matches",
            name,
        )
        return None
    if len(matches) > 1:
        logger.warning(
            "agent model ref %r: ambiguous — %d matches, using first (%s)",
            name,
            len(matches),
            matches[0][0].name,
        )
    return matches[0]
