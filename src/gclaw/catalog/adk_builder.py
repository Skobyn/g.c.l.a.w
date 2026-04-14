"""Shared ADK model object builder for catalog-backed providers.

Produces an ADK-ready model representation for a given (provider, model)
pair: either a bare model-id string (Gemini/Vertex) or a LiteLlm instance
(everything else). Used by both the router loader and the agent factory
so the two share a single wrapping convention.
"""

from __future__ import annotations

import logging
from typing import Any

from gclaw.models.catalog import ModelProvider, ModelRecord, ProviderKind

logger = logging.getLogger(__name__)


# LiteLLM provider prefixes for OpenAI-compatible providers.
_LITELLM_PREFIX: dict[ProviderKind, str] = {
    ProviderKind.OPENAI: "openai",
    ProviderKind.ANTHROPIC: "anthropic",
    ProviderKind.OPENROUTER: "openrouter",
    ProviderKind.GROQ: "groq",
    ProviderKind.TOGETHER: "together_ai",
    ProviderKind.CUSTOM_OPENAI: "openai",
    ProviderKind.OLLAMA: "ollama",
}


def build_adk_override_from_model(
    provider: ModelProvider,
    model: ModelRecord,
    api_key: str | None,
    extra_litellm_kwargs: dict[str, Any] | None = None,
) -> Any:
    """Build an ADK-ready model object from a catalog (provider, model).

    Returns a bare model-id string for Gemini/Vertex, otherwise a LiteLlm
    instance wrapping the provider prefix + model id + api_key/api_base.
    """
    if provider.kind in (ProviderKind.GOOGLE_GEMINI, ProviderKind.GOOGLE_VERTEX):
        return model.model_id

    prefix = _LITELLM_PREFIX.get(provider.kind)
    if prefix is None:
        logger.warning(
            "Unknown provider kind for LiteLlm wrapping: %s — using bare model id",
            provider.kind,
        )
        return model.model_id

    from google.adk.models.lite_llm import LiteLlm

    kwargs: dict[str, Any] = {"model": f"{prefix}/{model.model_id}"}
    if api_key:
        kwargs["api_key"] = api_key
    if provider.base_url:
        kwargs["api_base"] = provider.base_url
    if extra_litellm_kwargs:
        kwargs.update(extra_litellm_kwargs)
    return LiteLlm(**kwargs)
