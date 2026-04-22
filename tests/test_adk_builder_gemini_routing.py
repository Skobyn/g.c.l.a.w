"""Tests for Gemini provider routing in build_adk_override_from_model.

The catalog can register two distinct Gemini providers:

1. The implicit "System (Google)" provider (no api_key) — represents the
   Vertex AI path resolved via Application Default Credentials. Should
   return a bare model_id string so ADK uses the env-driven Vertex path.

2. The explicit "Google Gemini" provider (api_key) — represents the
   public Gemini API at generativelanguage.googleapis.com. Should return
   a LiteLlm wrapped with the `gemini/` prefix so the call goes via the
   public API regardless of the global GOOGLE_GENAI_USE_VERTEXAI setting
   — which is how preview models like gemini-3-pro-preview that exist on
   AI Studio but not yet on Vertex become reachable.
"""

from __future__ import annotations

from gclaw.catalog.adk_builder import build_adk_override_from_model
from gclaw.models.catalog import ModelProvider, ModelRecord, ProviderKind


def _make_model(model_id: str = "gemini-3-pro-preview") -> ModelRecord:
    return ModelRecord(
        provider_id="prov_test",
        model_id=model_id,
        display_name=model_id,
    )


def test_vertex_provider_returns_bare_model_id():
    """GOOGLE_VERTEX always returns the bare id; ADK uses env config."""
    provider = ModelProvider(name="Vertex", kind=ProviderKind.GOOGLE_VERTEX)
    result = build_adk_override_from_model(
        provider, _make_model("gemini-2.5-flash"), api_key=None,
    )
    assert result == "gemini-2.5-flash"


def test_gemini_provider_without_key_returns_bare_model_id():
    """No api_key → falls back to bare id (legacy ADC / env path).

    Preserves the existing "System (Google)" provider behavior so this
    change doesn't disturb callers who never registered an explicit key.
    """
    provider = ModelProvider(name="System Google", kind=ProviderKind.GOOGLE_GEMINI)
    result = build_adk_override_from_model(
        provider, _make_model("gemini-2.5-flash"), api_key=None,
    )
    assert result == "gemini-2.5-flash"


def test_gemini_provider_with_key_routes_via_litellm():
    """An api_key on the GOOGLE_GEMINI provider means "use the public
    AI Studio API" — wrap in LiteLlm with the `gemini/` prefix so the
    call bypasses the global GOOGLE_GENAI_USE_VERTEXAI=TRUE env."""
    from google.adk.models.lite_llm import LiteLlm

    provider = ModelProvider(
        name="Google Gemini (public)",
        kind=ProviderKind.GOOGLE_GEMINI,
    )
    result = build_adk_override_from_model(
        provider,
        _make_model("gemini-3-pro-preview"),
        api_key="AIza-test-key",
    )
    assert isinstance(result, LiteLlm)
    # LiteLlm stores the prefixed name in `model`.
    assert result.model == "gemini/gemini-3-pro-preview"
    # And keeps the api_key for the request.
    assert result._additional_args.get("api_key") == "AIza-test-key"


def test_gemini_provider_with_key_handles_preview_model():
    """Regression sanity-check: the whole point of this routing is to
    let preview models that aren't in Vertex (e.g. gemini-3.1-pro-preview
    as of 2026-04-22) work via the public API."""
    from google.adk.models.lite_llm import LiteLlm

    provider = ModelProvider(
        name="Google Gemini",
        kind=ProviderKind.GOOGLE_GEMINI,
    )
    result = build_adk_override_from_model(
        provider,
        _make_model("gemini-3.1-pro-preview"),
        api_key="AIza-x",
    )
    assert isinstance(result, LiteLlm)
    assert result.model == "gemini/gemini-3.1-pro-preview"
