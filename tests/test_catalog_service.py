"""Tests for CatalogService using in-memory fake repos."""

from __future__ import annotations

import os

import pytest

from gclaw.catalog.service import CatalogService
from gclaw.models.catalog import (
    ApiKeyKind,
    ApiKeySpec,
    Capabilities,
    ModelProvider,
    ModelRecord,
    ProviderKind,
)


from _catalog_fakes import FakeModelRepo, FakeProviderRepo


@pytest.fixture
def service():
    return CatalogService(
        provider_repo=FakeProviderRepo(),
        model_repo=FakeModelRepo(),
    )


def test_create_and_get_provider(service):
    p = service.create_provider(name="My OpenAI", kind=ProviderKind.OPENAI)
    assert p.id.startswith("prov_")
    got = service.get_provider(p.id)
    assert got is not None
    assert got.name == "My OpenAI"


def test_update_provider(service):
    p = service.create_provider(name="X", kind=ProviderKind.OPENAI)
    updated = service.update_provider(p.id, name="Y", enabled=False)
    assert updated.name == "Y"
    assert updated.enabled is False
    assert updated.id == p.id


def test_update_missing_provider_raises(service):
    with pytest.raises(ValueError):
        service.update_provider("prov_nope", name="Z")


def test_delete_provider_cascades_models(service):
    p = service.create_provider(name="X", kind=ProviderKind.OPENAI)
    m1 = service.create_model(provider_id=p.id, model_id="a", display_name="A")
    m2 = service.create_model(provider_id=p.id, model_id="b", display_name="B")
    # Unrelated provider's models should survive
    p2 = service.create_provider(name="Y", kind=ProviderKind.ANTHROPIC)
    m3 = service.create_model(provider_id=p2.id, model_id="c", display_name="C")

    service.delete_provider(p.id)

    assert service.get_provider(p.id) is None
    assert service.get_model(m1.id) is None
    assert service.get_model(m2.id) is None
    assert service.get_model(m3.id) is not None


def test_create_model_unknown_provider(service):
    with pytest.raises(ValueError):
        service.create_model(
            provider_id="prov_nope", model_id="x", display_name="X"
        )


def test_list_models_by_provider(service):
    p1 = service.create_provider(name="a", kind=ProviderKind.OPENAI)
    p2 = service.create_provider(name="b", kind=ProviderKind.ANTHROPIC)
    service.create_model(provider_id=p1.id, model_id="m1", display_name="M1")
    service.create_model(provider_id=p2.id, model_id="m2", display_name="M2")
    assert len(service.list_models(provider_id=p1.id)) == 1
    assert len(service.list_models()) == 2


def test_resolve_api_key_literal(service):
    p = service.create_provider(
        name="x",
        kind=ProviderKind.OPENAI,
        api_key=ApiKeySpec(kind=ApiKeyKind.LITERAL, value="sk-123"),
    )
    assert service.resolve_api_key(p) == "sk-123"


def test_resolve_api_key_env(service, monkeypatch):
    monkeypatch.setenv("MY_TEST_KEY", "value-from-env")
    p = service.create_provider(
        name="x",
        kind=ProviderKind.OPENAI,
        api_key=ApiKeySpec(kind=ApiKeyKind.ENV, value="MY_TEST_KEY"),
    )
    assert service.resolve_api_key(p) == "value-from-env"


def test_resolve_api_key_env_missing(service, monkeypatch):
    monkeypatch.delenv("MISSING_KEY_XYZ", raising=False)
    p = service.create_provider(
        name="x",
        kind=ProviderKind.OPENAI,
        api_key=ApiKeySpec(kind=ApiKeyKind.ENV, value="MISSING_KEY_XYZ"),
    )
    assert service.resolve_api_key(p) is None


def test_resolve_api_key_secret_manager_placeholder(service):
    p = service.create_provider(
        name="x",
        kind=ProviderKind.OPENAI,
        api_key=ApiKeySpec(
            kind=ApiKeyKind.SECRET_MANAGER,
            value="projects/x/secrets/y/versions/latest",
        ),
    )
    assert service.resolve_api_key(p) is None


def test_resolve_api_key_none(service):
    p = service.create_provider(name="x", kind=ProviderKind.OLLAMA)
    assert service.resolve_api_key(p) is None


def test_resolve_api_key_anthropic_oauth_with_manager():
    """ANTHROPIC_OAUTH provider returns .access_token via oauth_manager."""
    import asyncio

    class FakeManager:
        def __init__(self):
            self.calls: list[str] = []

        async def get_access_token(self, sm_path: str):
            self.calls.append(sm_path)
            return "refreshed-access-token"

    mgr = FakeManager()
    service = CatalogService(
        provider_repo=FakeProviderRepo(),
        model_repo=FakeModelRepo(),
        oauth_manager=mgr,
    )
    p = service.create_provider(
        name="claude-oauth",
        kind=ProviderKind.ANTHROPIC_OAUTH,
        api_key=ApiKeySpec(
            kind=ApiKeyKind.SECRET_MANAGER,
            value="projects/p/secrets/watson-c/versions/latest",
        ),
    )
    assert service.resolve_api_key(p) == "refreshed-access-token"
    assert mgr.calls == ["projects/p/secrets/watson-c/versions/latest"]


def test_resolve_api_key_anthropic_oauth_without_manager_parses_json(monkeypatch):
    """Without oauth_manager wired, resolve_api_key falls back to SM read +
    JSON parse and returns .access_token."""
    import json
    from datetime import datetime, timedelta, timezone

    service = CatalogService(
        provider_repo=FakeProviderRepo(),
        model_repo=FakeModelRepo(),
    )

    bundle_json = json.dumps({
        "access_token": "json-access",
        "refresh_token": "r",
        "expires_at": (
            datetime.now(timezone.utc) + timedelta(hours=1)
        ).isoformat(),
    })

    def fake_raw_read(self, sm_path, provider_name):
        return bundle_json

    monkeypatch.setattr(
        CatalogService, "_raw_sm_read", fake_raw_read, raising=True
    )

    p = service.create_provider(
        name="claude-oauth",
        kind=ProviderKind.ANTHROPIC_OAUTH,
        api_key=ApiKeySpec(
            kind=ApiKeyKind.SECRET_MANAGER,
            value="projects/p/secrets/watson-c/versions/latest",
        ),
    )
    assert service.resolve_api_key(p) == "json-access"


def test_update_model(service):
    p = service.create_provider(name="x", kind=ProviderKind.OPENAI)
    m = service.create_model(provider_id=p.id, model_id="a", display_name="A")
    updated = service.update_model(
        m.id,
        display_name="AA",
        capabilities={"vision": True, "tools": True},
    )
    assert updated.display_name == "AA"
    assert updated.capabilities.vision is True
