"""Connectivity test for providers/models.

Makes a minimal ``ping`` call appropriate for the provider kind and
returns a small result dict. Never raises — errors are captured in
``{ok: False, error: ...}``.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from gclaw.models.catalog import (
    ApiKeyKind,
    ModelProvider,
    ModelRecord,
    ProviderKind,
)

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 10.0

_OPENAI_COMPAT_KINDS = {
    ProviderKind.OPENAI,
    ProviderKind.OPENROUTER,
    ProviderKind.GROQ,
    ProviderKind.TOGETHER,
    ProviderKind.CUSTOM_OPENAI,
    ProviderKind.OLLAMA,
}

_DEFAULT_BASE_URLS = {
    ProviderKind.OPENAI: "https://api.openai.com/v1",
    ProviderKind.OPENROUTER: "https://openrouter.ai/api/v1",
    ProviderKind.GROQ: "https://api.groq.com/openai/v1",
    ProviderKind.TOGETHER: "https://api.together.xyz/v1",
    ProviderKind.OLLAMA: "http://localhost:11434",
    ProviderKind.ANTHROPIC: "https://api.anthropic.com",
}


def _resolve_key(provider: ModelProvider) -> str | None:
    """Fallback local resolver. Handles LITERAL and ENV only.

    Secret-Manager-backed keys (including OAuth-refreshed tokens) must be
    resolved by the caller via ``CatalogService.resolve_api_key`` and passed
    into ``test_connection`` as ``resolved_key`` — that path has SM reader
    and OAuth token-manager integration this module can't replicate.
    """
    spec = provider.api_key
    if spec is None:
        return None
    if spec.kind == ApiKeyKind.LITERAL:
        return spec.value
    if spec.kind == ApiKeyKind.ENV:
        import os
        return os.environ.get(spec.value)
    return None


def _result(
    ok: bool,
    *,
    latency_ms: float,
    error: str | None = None,
    sample_response: Any = None,
) -> dict:
    return {
        "ok": ok,
        "latency_ms": round(latency_ms, 2),
        "error": error,
        "sample_response": sample_response,
    }


async def test_connection(
    provider: ModelProvider,
    model: ModelRecord,
    *,
    resolved_key: str | None = None,
) -> dict:
    """Make a minimal request against ``provider``/``model``.

    When ``resolved_key`` is provided, it is used verbatim — this is the
    canonical path because ``CatalogService.resolve_api_key`` handles
    SECRET_MANAGER and OAuth tokens. When omitted, falls back to a local
    LITERAL/ENV-only resolver.

    Returns a JSON-serializable dict with keys:
      ok, latency_ms, error, sample_response
    """
    start = time.perf_counter()
    key = resolved_key if resolved_key is not None else _resolve_key(provider)
    try:
        if provider.kind in _OPENAI_COMPAT_KINDS:
            return await _test_openai_compat(provider, model, start, key)
        if provider.kind == ProviderKind.ANTHROPIC:
            return await _test_anthropic(provider, model, start, key)
        if provider.kind == ProviderKind.ANTHROPIC_OAUTH:
            return await _test_anthropic_oauth(provider, model, start, key)
        if provider.kind == ProviderKind.GOOGLE_GEMINI:
            return await _test_google_gemini(provider, model, start, key)
        if provider.kind == ProviderKind.GOOGLE_VERTEX:
            return await _test_google_vertex(provider, model, start)
        latency = (time.perf_counter() - start) * 1000
        return _result(
            False,
            latency_ms=latency,
            error=f"Unsupported provider kind: {provider.kind.value}",
        )
    except Exception as e:  # noqa: BLE001 — user-facing summary
        latency = (time.perf_counter() - start) * 1000
        return _result(False, latency_ms=latency, error=str(e))


async def _test_openai_compat(
    provider: ModelProvider, model: ModelRecord, start: float, key: str | None
) -> dict:
    base_url = provider.base_url or _DEFAULT_BASE_URLS.get(provider.kind)
    if not base_url:
        latency = (time.perf_counter() - start) * 1000
        return _result(False, latency_ms=latency, error="No base_url configured")

    headers = {"Content-Type": "application/json", **provider.default_headers}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    chat_url = base_url.rstrip("/") + "/chat/completions"
    chat_body = {
        "model": model.model_id,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 5,
    }

    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
        resp = await client.post(chat_url, json=chat_body, headers=headers)
        # Some models (notably GitHub Copilot's codex family) reject
        # /chat/completions with unsupported_api_for_model and require the
        # Responses API. Retry transparently on that signal.
        if resp.status_code == 400 and "unsupported_api_for_model" in resp.text:
            resp_url = base_url.rstrip("/") + "/responses"
            resp_body = {
                "model": model.model_id,
                "input": "ping",
                "max_output_tokens": 16,
            }
            resp = await client.post(resp_url, json=resp_body, headers=headers)

    latency = (time.perf_counter() - start) * 1000
    if resp.status_code >= 400:
        return _result(
            False,
            latency_ms=latency,
            error=f"HTTP {resp.status_code}: {resp.text[:200]}",
        )
    try:
        data = resp.json()
    except Exception:
        data = {"raw": resp.text[:200]}
    return _result(True, latency_ms=latency, sample_response=data)


async def _test_anthropic(
    provider: ModelProvider, model: ModelRecord, start: float, key: str | None
) -> dict:
    base_url = provider.base_url or _DEFAULT_BASE_URLS[ProviderKind.ANTHROPIC]
    url = base_url.rstrip("/") + "/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
        **provider.default_headers,
    }
    if key:
        headers["x-api-key"] = key
    body = {
        "model": model.model_id,
        "max_tokens": 5,
        "messages": [{"role": "user", "content": "ping"}],
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
        resp = await client.post(url, json=body, headers=headers)
    latency = (time.perf_counter() - start) * 1000
    if resp.status_code >= 400:
        return _result(
            False,
            latency_ms=latency,
            error=f"HTTP {resp.status_code}: {resp.text[:200]}",
        )
    try:
        data = resp.json()
    except Exception:
        data = {"raw": resp.text[:200]}
    return _result(True, latency_ms=latency, sample_response=data)


async def _test_anthropic_oauth(
    provider: ModelProvider, model: ModelRecord, start: float, key: str | None
) -> dict:
    base_url = provider.base_url or _DEFAULT_BASE_URLS[ProviderKind.ANTHROPIC]
    url = base_url.rstrip("/") + "/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
        "anthropic-beta": "oauth-2025-04-20",
        **provider.default_headers,
    }
    if key:
        headers["Authorization"] = f"Bearer {key}"
    # Claude Code OAuth tokens require the request to identify itself as
    # Claude Code via a system prompt. Without it Anthropic silently
    # rate-limits (HTTP 429 with a blank "Error" message) on higher-tier
    # models like opus/sonnet — haiku tolerates the missing identifier.
    body = {
        "model": model.model_id,
        "max_tokens": 5,
        "system": "You are Claude Code, Anthropic's official CLI for Claude.",
        "messages": [{"role": "user", "content": "ping"}],
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
        resp = await client.post(url, json=body, headers=headers)
    latency = (time.perf_counter() - start) * 1000
    if resp.status_code >= 400:
        return _result(
            False,
            latency_ms=latency,
            error=f"HTTP {resp.status_code}: {resp.text[:200]}",
        )
    try:
        data = resp.json()
    except Exception:
        data = {"raw": resp.text[:200]}
    return _result(True, latency_ms=latency, sample_response=data)


async def _test_google_gemini(
    provider: ModelProvider, model: ModelRecord, start: float, key: str | None
) -> dict:
    if not key:
        latency = (time.perf_counter() - start) * 1000
        return _result(
            False,
            latency_ms=latency,
            error="google_gemini requires an API key",
        )
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model.model_id}:generateContent?key={key}"
    )
    body = {"contents": [{"parts": [{"text": "ping"}]}]}
    headers = {"Content-Type": "application/json", **provider.default_headers}
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
        resp = await client.post(url, json=body, headers=headers)
    latency = (time.perf_counter() - start) * 1000
    if resp.status_code >= 400:
        return _result(
            False,
            latency_ms=latency,
            error=f"HTTP {resp.status_code}: {resp.text[:200]}",
        )
    try:
        data = resp.json()
    except Exception:
        data = {"raw": resp.text[:200]}
    return _result(True, latency_ms=latency, sample_response=data)


async def _test_google_vertex(
    provider: ModelProvider, model: ModelRecord, start: float
) -> dict:
    try:
        from google import genai  # type: ignore
    except Exception as e:  # noqa: BLE001
        latency = (time.perf_counter() - start) * 1000
        return _result(
            False,
            latency_ms=latency,
            error=f"google-genai not installed: {e}",
        )

    try:
        client = genai.Client(vertexai=True)
        # Minimal generate call — any error here (creds, model, etc.)
        # surfaces as ok=False below.
        response = client.models.generate_content(
            model=model.model_id,
            contents="ping",
        )
        latency = (time.perf_counter() - start) * 1000
        text = getattr(response, "text", None) or str(response)[:200]
        return _result(True, latency_ms=latency, sample_response={"text": text})
    except Exception as e:  # noqa: BLE001
        latency = (time.perf_counter() - start) * 1000
        return _result(False, latency_ms=latency, error=str(e))
