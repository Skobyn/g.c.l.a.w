"""Tests for gclaw.catalog.test_connection — HTTP mocked with httpx."""

from __future__ import annotations

import httpx
import pytest

from gclaw.catalog.test_connection import test_connection as run_connection_test
from gclaw.models.catalog import (
    ApiKeyKind,
    ApiKeySpec,
    ModelProvider,
    ModelRecord,
    ProviderKind,
)


def _mount(monkeypatch, handler):
    """Install a mock transport on httpx.AsyncClient for one test."""
    original_init = httpx.AsyncClient.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)


@pytest.mark.asyncio
async def test_openai_compat_success(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        captured["body"] = request.content
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "pong"}}]}
        )

    _mount(monkeypatch, handler)

    provider = ModelProvider(
        name="OAI",
        kind=ProviderKind.OPENAI,
        base_url="https://api.openai.com/v1",
        api_key=ApiKeySpec(kind=ApiKeyKind.LITERAL, value="sk-test"),
    )
    model = ModelRecord(provider_id=provider.id, model_id="gpt-4o", display_name="GPT-4o")

    result = await run_connection_test(provider, model)
    assert result["ok"] is True
    assert result["error"] is None
    assert "https://api.openai.com/v1/chat/completions" in captured["url"]
    assert captured["auth"] == "Bearer sk-test"
    assert b"gpt-4o" in captured["body"]


@pytest.mark.asyncio
async def test_openai_compat_http_error(monkeypatch):
    def handler(request):
        return httpx.Response(401, text="unauthorized")

    _mount(monkeypatch, handler)

    provider = ModelProvider(
        name="OAI",
        kind=ProviderKind.OPENAI,
        base_url="https://api.openai.com/v1",
    )
    model = ModelRecord(provider_id=provider.id, model_id="gpt-4o", display_name="x")
    result = await run_connection_test(provider, model)
    assert result["ok"] is False
    assert "401" in result["error"]


@pytest.mark.asyncio
async def test_anthropic_sends_correct_headers(monkeypatch):
    captured: dict = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["x_api_key"] = request.headers.get("x-api-key")
        captured["version"] = request.headers.get("anthropic-version")
        return httpx.Response(200, json={"content": [{"text": "pong"}]})

    _mount(monkeypatch, handler)

    provider = ModelProvider(
        name="Anth",
        kind=ProviderKind.ANTHROPIC,
        api_key=ApiKeySpec(kind=ApiKeyKind.LITERAL, value="sk-ant-xyz"),
    )
    model = ModelRecord(
        provider_id=provider.id, model_id="claude-opus-4-6", display_name="x"
    )

    result = await run_connection_test(provider, model)
    assert result["ok"] is True
    assert captured["url"].endswith("/v1/messages")
    assert captured["x_api_key"] == "sk-ant-xyz"
    assert captured["version"] == "2023-06-01"


@pytest.mark.asyncio
async def test_gemini_uses_key_query_param(monkeypatch):
    captured: dict = {}

    def handler(request):
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "pong"}]}}]})

    _mount(monkeypatch, handler)

    provider = ModelProvider(
        name="G",
        kind=ProviderKind.GOOGLE_GEMINI,
        api_key=ApiKeySpec(kind=ApiKeyKind.LITERAL, value="AIza-test"),
    )
    model = ModelRecord(provider_id=provider.id, model_id="gemini-2.5-flash", display_name="x")
    result = await run_connection_test(provider, model)
    assert result["ok"] is True
    assert "generativelanguage.googleapis.com" in captured["url"]
    assert "key=AIza-test" in captured["url"]
    assert "gemini-2.5-flash:generateContent" in captured["url"]


@pytest.mark.asyncio
async def test_gemini_requires_key():
    provider = ModelProvider(name="G", kind=ProviderKind.GOOGLE_GEMINI)
    model = ModelRecord(provider_id=provider.id, model_id="gemini-2.5-flash", display_name="x")
    result = await run_connection_test(provider, model)
    assert result["ok"] is False
    assert "API key" in result["error"]


@pytest.mark.asyncio
async def test_openrouter_uses_default_base_url(monkeypatch):
    captured: dict = {}

    def handler(request):
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"ok": True})

    _mount(monkeypatch, handler)

    provider = ModelProvider(
        name="OR",
        kind=ProviderKind.OPENROUTER,
        api_key=ApiKeySpec(kind=ApiKeyKind.LITERAL, value="or-key"),
    )
    model = ModelRecord(
        provider_id=provider.id,
        model_id="meta-llama/llama-3.3-70b-instruct",
        display_name="x",
    )
    result = await run_connection_test(provider, model)
    assert result["ok"] is True
    assert "openrouter.ai/api/v1/chat/completions" in captured["url"]


@pytest.mark.asyncio
async def test_network_error_captured(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("boom")

    _mount(monkeypatch, handler)

    provider = ModelProvider(
        name="x",
        kind=ProviderKind.OPENAI,
        base_url="https://api.openai.com/v1",
    )
    model = ModelRecord(provider_id=provider.id, model_id="m", display_name="x")
    result = await run_connection_test(provider, model)
    assert result["ok"] is False
    assert "boom" in result["error"]
