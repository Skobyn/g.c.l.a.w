"""Tests for build_endpoints_from_catalog — verifies LiteLlm wrapping."""

from __future__ import annotations

import pytest

from gclaw.catalog.service import CatalogService
from gclaw.models.catalog import (
    ApiKeyKind,
    ApiKeySpec,
    ProviderKind,
)
from gclaw.routing.catalog_loader import load_endpoints_from_catalog
from _catalog_fakes import FakeModelRepo, FakeProviderRepo


@pytest.fixture
def populated_service():
    svc = CatalogService(
        provider_repo=FakeProviderRepo(),
        model_repo=FakeModelRepo(),
    )
    oai = svc.create_provider(
        name="OAI",
        kind=ProviderKind.OPENAI,
        base_url="https://api.openai.com/v1",
        api_key=ApiKeySpec(kind=ApiKeyKind.LITERAL, value="sk-oai"),
    )
    anth = svc.create_provider(
        name="Anth",
        kind=ProviderKind.ANTHROPIC,
        api_key=ApiKeySpec(kind=ApiKeyKind.LITERAL, value="sk-anth"),
    )
    gem = svc.create_provider(name="G", kind=ProviderKind.GOOGLE_GEMINI)
    svc.create_model(
        provider_id=oai.id, model_id="gpt-4o", display_name="GPT-4o",
        context_window=128000,
    )
    svc.create_model(
        provider_id=anth.id, model_id="claude-opus-4-6",
        display_name="Opus 4.6",
    )
    svc.create_model(
        provider_id=gem.id, model_id="gemini-2.5-flash",
        display_name="Gemini 2.5 Flash",
    )
    return svc, oai, anth, gem


def test_builds_endpoints_for_each_enabled_model(populated_service):
    svc, oai, anth, gem = populated_service
    router = load_endpoints_from_catalog(svc, fallback_flash_model="gemini-2.5-flash")
    endpoints = router.list_endpoints()
    assert len(endpoints) == 3
    assert "OAI/gpt-4o" in endpoints
    assert "Anth/claude-opus-4-6" in endpoints
    assert "G/gemini-2.5-flash" in endpoints


def test_gemini_provider_returns_bare_string(populated_service):
    svc, _oai, _anth, _gem = populated_service
    router = load_endpoints_from_catalog(svc, fallback_flash_model="gemini-2.5-flash")
    obj = router._adk_overrides["G/gemini-2.5-flash"]  # type: ignore[attr-defined]
    assert obj == "gemini-2.5-flash"


def test_openai_provider_wrapped_as_litellm(populated_service):
    svc, _oai, _anth, _gem = populated_service
    router = load_endpoints_from_catalog(svc, fallback_flash_model="gemini-2.5-flash")
    obj = router._adk_overrides["OAI/gpt-4o"]  # type: ignore[attr-defined]

    from google.adk.models.lite_llm import LiteLlm
    assert isinstance(obj, LiteLlm)
    # LiteLlm stores the model string; check prefix
    assert "openai/gpt-4o" in str(getattr(obj, "model", ""))


def test_anthropic_provider_wrapped_as_litellm(populated_service):
    svc, _oai, _anth, _gem = populated_service
    router = load_endpoints_from_catalog(svc, fallback_flash_model="gemini-2.5-flash")
    obj = router._adk_overrides["Anth/claude-opus-4-6"]  # type: ignore[attr-defined]

    from google.adk.models.lite_llm import LiteLlm
    assert isinstance(obj, LiteLlm)
    assert "anthropic/claude-opus-4-6" in str(getattr(obj, "model", ""))


def test_anthropic_oauth_provider_lets_litellm_emit_authorization():
    """Anthropic OAuth path must NOT inject `Authorization: Bearer ...`
    via extra_headers. LiteLlm's Anthropic transformer auto-emits the
    Bearer header from `api_key` for sk-ant-oat* tokens. If we ALSO put
    Authorization in extra_headers, httpx merges both into a single
    comma-joined value (`Bearer foo, Bearer foo`) and Anthropic 401s
    with "Invalid bearer token". So the contract is:
      * api_key carries the token
      * extra_headers carries ONLY anthropic-beta (the OAuth scope flag)
      * LiteLlm produces the actual Authorization header at call time
    """
    svc = CatalogService(
        provider_repo=FakeProviderRepo(),
        model_repo=FakeModelRepo(),
    )
    oauth = svc.create_provider(
        name="CC",
        kind=ProviderKind.ANTHROPIC_OAUTH,
        api_key=ApiKeySpec(kind=ApiKeyKind.LITERAL, value="sk-ant-oat-xyz"),
    )
    svc.create_model(
        provider_id=oauth.id,
        model_id="claude-sonnet-4-6",
        display_name="Sonnet OAuth",
    )
    router = load_endpoints_from_catalog(svc, fallback_flash_model="gemini-2.5-flash")
    obj = router._adk_overrides["CC/claude-sonnet-4-6"]  # type: ignore[attr-defined]

    from google.adk.models.lite_llm import LiteLlm
    assert isinstance(obj, LiteLlm)
    assert "anthropic/claude-sonnet-4-6" in str(getattr(obj, "model", ""))

    extra = getattr(obj, "_additional_args", None) or {}
    # api_key must be the OAuth token (not lost in the rename) so LiteLlm
    # can emit the right Authorization header at request time.
    assert extra.get("api_key") == "sk-ant-oat-xyz", (
        f"expected api_key=sk-ant-oat-xyz on LiteLlm kwargs; got {extra!r}"
    )
    # extra_headers must carry the OAuth scope flag…
    headers = extra.get("extra_headers") or {}
    assert headers.get("anthropic-beta") == "oauth-2025-04-20"
    # …and MUST NOT carry Authorization (would duplicate LiteLlm's auto-injection).
    assert "Authorization" not in headers, (
        "Authorization in extra_headers duplicates LiteLlm's auto-injected "
        "Bearer header → Anthropic returns 401. See adk_builder.py."
    )


def test_disabled_models_excluded():
    svc = CatalogService(
        provider_repo=FakeProviderRepo(),
        model_repo=FakeModelRepo(),
    )
    p = svc.create_provider(name="P", kind=ProviderKind.OPENAI)
    svc.create_model(provider_id=p.id, model_id="a", display_name="A", enabled=False)
    svc.create_model(provider_id=p.id, model_id="b", display_name="B")
    router = load_endpoints_from_catalog(svc, fallback_flash_model="gemini-2.5-flash")
    endpoints = router.list_endpoints()
    assert len(endpoints) == 1
    assert "P/b" in endpoints


def test_disabled_provider_excludes_all_its_models():
    svc = CatalogService(
        provider_repo=FakeProviderRepo(),
        model_repo=FakeModelRepo(),
    )
    p = svc.create_provider(name="P", kind=ProviderKind.OPENAI, enabled=False)
    svc.create_model(provider_id=p.id, model_id="a", display_name="A")
    router = load_endpoints_from_catalog(svc, fallback_flash_model="gemini-2.5-flash")
    assert router.list_endpoints() == {}
