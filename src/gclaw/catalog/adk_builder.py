"""Shared ADK model object builder for catalog-backed providers.

Produces an ADK-ready model representation for a given (provider, model)
pair: either a bare model-id string (Gemini/Vertex) or a LiteLlm instance
(everything else). Used by both the router loader and the agent factory
so the two share a single wrapping convention.

OAuth-backed providers — Anthropic Claude-Code OAuth, GitHub Copilot
via the token-exchange — get a ``_RefreshingLiteLlm`` subclass that
re-resolves credentials on every ``generate_content_async`` call. The
default ``LiteLlm`` bakes ``api_key`` / ``extra_headers`` into
``self._additional_args`` once at construction, which goes stale the
moment the underlying token rotates — for Anthropic after ~8 hours,
for Copilot after ~30 minutes. The refreshing variant reads fresh
credentials via a caller-supplied callable each request.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from gclaw.models.catalog import ModelProvider, ModelRecord, ProviderKind

logger = logging.getLogger(__name__)


def _build_refreshing_litellm_class():
    """Build and return the refreshing LiteLlm subclass lazily.

    Defined inside a function so ``google-adk`` stays an optional import
    for callers of this module that only want ``build_adk_override_from_model``
    to choose between bare-string and LiteLlm paths. The class is cached
    on the function object so subsequent calls reuse it.
    """
    existing = getattr(_build_refreshing_litellm_class, "_cls", None)
    if existing is not None:
        return existing

    from google.adk.models.lite_llm import LiteLlm

    class _RefreshingLiteLlm(LiteLlm):
        """LiteLlm subclass that refreshes auth each generate call.

        Constructed with a ``refresh_fn: Callable[[], dict]`` which must
        return a patch dict applied to ``self._additional_args`` before
        every ``generate_content_async`` invocation. Typical patch
        shapes:
          - ``{"api_key": "sk-…"}`` (OpenAI-compatible providers)
          - ``{"extra_headers": {"Authorization": "Bearer …"}}``
            (Anthropic OAuth)

        A refresh_fn exception is logged and skipped — the call proceeds
        with the last-known credentials rather than 500ing outright.
        """

        _refresh_fn: Any = None

        def __init__(self, *, refresh_fn, **kwargs):
            super().__init__(**kwargs)
            # Pydantic private attrs need assignment via object.__setattr__
            # when the class uses slots / strict validation; a plain
            # attribute set works under default BaseModel.
            object.__setattr__(self, "_refresh_fn", refresh_fn)

        async def generate_content_async(self, llm_request, stream: bool = False):
            fn = object.__getattribute__(self, "_refresh_fn")
            if fn is not None:
                try:
                    patch = fn() or {}
                except Exception:
                    logger.warning(
                        "refreshing-litellm: refresh_fn raised; proceeding "
                        "with stale credentials",
                        exc_info=True,
                    )
                    patch = {}
                if isinstance(patch, dict) and patch:
                    existing_args = self._additional_args or {}
                    # Merge extra_headers field-by-field to preserve any
                    # non-auth headers (anthropic-version, Copilot-*).
                    if "extra_headers" in patch and isinstance(
                        patch["extra_headers"], dict
                    ):
                        merged = dict(existing_args.get("extra_headers") or {})
                        merged.update(patch["extra_headers"])
                        existing_args["extra_headers"] = merged
                    for k, v in patch.items():
                        if k == "extra_headers":
                            continue
                        existing_args[k] = v
                    self._additional_args = existing_args

            async for resp in super().generate_content_async(
                llm_request, stream=stream
            ):
                yield resp

    _build_refreshing_litellm_class._cls = _RefreshingLiteLlm
    return _RefreshingLiteLlm


# LiteLLM provider prefixes for OpenAI-compatible providers.
_LITELLM_PREFIX: dict[ProviderKind, str] = {
    ProviderKind.OPENAI: "openai",
    ProviderKind.ANTHROPIC: "anthropic",
    ProviderKind.ANTHROPIC_OAUTH: "anthropic",
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
    key_provider: Callable[[], str | None] | None = None,
) -> Any:
    """Build an ADK-ready model object from a catalog (provider, model).

    Returns a bare model-id string for Gemini/Vertex, otherwise a
    LiteLlm (or refreshing subclass) wrapping provider prefix + model
    id + api_key/api_base.

    ``key_provider`` is an optional zero-arg callable returning the
    current api_key for this provider. When supplied AND the provider
    kind is known to rotate tokens (ANTHROPIC_OAUTH or Copilot-hosted
    CUSTOM_OPENAI), the returned LiteLlm is a refreshing subclass that
    re-invokes the callable on every generate call. For static-key
    providers the callable is ignored — there's no token to rotate.
    """
    # Google Vertex: bare model_id; ADK uses the env-driven Vertex path
    # (GOOGLE_GENAI_USE_VERTEXAI=TRUE + GOOGLE_CLOUD_PROJECT/LOCATION).
    # This is the right path for first-party publisher models that the
    # project is allowlisted for via Vertex.
    if provider.kind == ProviderKind.GOOGLE_VERTEX:
        return model.model_id

    # Google Gemini (public API at generativelanguage.googleapis.com):
    # the catalog can register the public-API provider with an explicit
    # api_key. We route this through LiteLlm's `gemini/` prefix so the
    # call goes via the public API regardless of the global
    # GOOGLE_GENAI_USE_VERTEXAI setting. This is how preview models like
    # `gemini-3-pro-preview` (which exist on AI Studio but not yet on
    # Vertex for many projects) become reachable.
    #
    # When no api_key is configured (the implicit "System (Google)"
    # provider that just uses ADC), fall back to bare model_id and let
    # ADK pick the env-driven path — preserves the legacy default.
    if provider.kind == ProviderKind.GOOGLE_GEMINI:
        if not api_key:
            return model.model_id
        from google.adk.models.lite_llm import LiteLlm
        return LiteLlm(model=f"gemini/{model.model_id}", api_key=api_key)

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

    # ANTHROPIC_OAUTH: Claude Code OAuth bearer token path.
    #
    # LiteLlm's Anthropic transformer detects sk-ant-oat* tokens from
    # `api_key` and emits `Authorization: Bearer <token>` itself. If we
    # ALSO put `Authorization` in extra_headers, httpx merges the two
    # values into a single comma-joined header
    # (`Authorization: Bearer foo, Bearer foo`) and Anthropic returns
    # 401 "Invalid bearer token". So for the standard sk-ant-oat path we
    # ONLY supply the OAuth beta header and let api_key drive the
    # Authorization header. Direct curl with the same token confirmed
    # the duplicate-header symptom.
    #
    # If you ever need to support a non-sk-ant-oat OAuth token shape,
    # branch on prefix and force Bearer via extra_headers ONLY in that
    # case (and clear api_key in the same kwargs). Don't combine.
    if provider.kind == ProviderKind.ANTHROPIC_OAUTH and api_key:
        kwargs["extra_headers"] = {
            "anthropic-beta": "oauth-2025-04-20",
        }

    # Copilot needs IDE-auth headers regardless of the auth-refresh
    # story — bake them in once here so they ride on every call.
    is_copilot = (
        provider.kind == ProviderKind.CUSTOM_OPENAI
        and "githubcopilot.com" in (provider.base_url or "").lower()
    )
    if is_copilot:
        existing = kwargs.get("extra_headers") or {}
        existing.setdefault("Editor-Version", "vscode/1.95.0")
        existing.setdefault("Copilot-Integration-Id", "vscode-chat")
        kwargs["extra_headers"] = existing

    if extra_litellm_kwargs:
        kwargs.update(extra_litellm_kwargs)

    # Refresh wiring: only for kinds whose creds rotate during an
    # agent's lifetime. Without this, api_key/extra_headers frozen at
    # construction cause 401s after token expiry (Anthropic ~8h,
    # Copilot session token ~30m).
    needs_refresh = (
        key_provider is not None
        and (provider.kind == ProviderKind.ANTHROPIC_OAUTH or is_copilot)
    )
    if needs_refresh:
        prov_kind = provider.kind

        def _refresh_fn() -> dict[str, Any]:
            try:
                fresh = key_provider()  # type: ignore[misc]
            except Exception:
                logger.warning(
                    "adk_builder: key_provider raised during refresh",
                    exc_info=True,
                )
                return {}
            if not fresh:
                return {}
            if prov_kind == ProviderKind.ANTHROPIC_OAUTH:
                # Same duplicate-Authorization gotcha as the construction
                # path above: api_key alone drives Authorization for
                # sk-ant-oat tokens. Patch api_key here, NOT
                # extra_headers["Authorization"], or you'll get
                # "Bearer foo, Bearer foo" → 401.
                return {"api_key": fresh}
            # Copilot-hosted CUSTOM_OPENAI
            return {"api_key": fresh}

        cls = _build_refreshing_litellm_class()
        return cls(refresh_fn=_refresh_fn, **kwargs)

    return LiteLlm(**kwargs)
