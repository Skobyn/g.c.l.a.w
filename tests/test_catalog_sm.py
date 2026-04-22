"""Tests for Secret Manager-backed API key resolution."""

from __future__ import annotations

import logging
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from gclaw.catalog.service import CatalogService
from gclaw.models.catalog import (
    ApiKeyKind,
    ApiKeySpec,
    ModelProvider,
    ProviderKind,
)

from _catalog_fakes import FakeModelRepo, FakeProviderRepo


def _provider_with_sm(name: str) -> ModelProvider:
    return ModelProvider(
        name="prov",
        kind=ProviderKind.OPENAI,
        api_key=ApiKeySpec(kind=ApiKeyKind.SECRET_MANAGER, value=name),
    )


class _FakeContext:
    def __init__(self, client_factory):
        self.client_factory = client_factory
        self._patches: list = []

    def __enter__(self):
        import google.cloud as gcloud_pkg
        fake_mod = types.ModuleType("google.cloud.secretmanager")
        fake_mod.SecretManagerServiceClient = self.client_factory
        p1 = patch.dict(sys.modules, {"google.cloud.secretmanager": fake_mod})
        p2 = patch.object(
            gcloud_pkg, "secretmanager", fake_mod, create=True
        )
        self._patches = [p1, p2]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self._patches):
            p.stop()
        return False


def _install_fake_secretmanager(client_factory):
    return _FakeContext(client_factory)


def test_resolve_api_key_sm_returns_decoded_string():
    svc = CatalogService(FakeProviderRepo(), FakeModelRepo())
    provider = _provider_with_sm(
        "projects/test-project/secrets/openai-key/versions/latest"
    )

    fake_client = MagicMock()
    fake_payload = MagicMock()
    fake_payload.data = b"sk-abc123"
    fake_response = MagicMock()
    fake_response.payload = fake_payload
    fake_client.access_secret_version.return_value = fake_response

    with _install_fake_secretmanager(lambda: fake_client):
        result = svc.resolve_api_key(provider)

    assert result == "sk-abc123"
    fake_client.access_secret_version.assert_called_once_with(
        name="projects/test-project/secrets/openai-key/versions/latest"
    )


def test_resolve_api_key_sm_client_cached():
    svc = CatalogService(FakeProviderRepo(), FakeModelRepo())
    provider = _provider_with_sm("projects/p/secrets/s/versions/latest")

    fake_client = MagicMock()
    fake_payload = MagicMock()
    fake_payload.data = b"value"
    fake_client.access_secret_version.return_value = MagicMock(payload=fake_payload)

    factory = MagicMock(return_value=fake_client)
    with _install_fake_secretmanager(factory):
        svc.resolve_api_key(provider)
        svc.resolve_api_key(provider)

    # Client constructed once even across two calls.
    assert factory.call_count == 1
    assert fake_client.access_secret_version.call_count == 2


def test_resolve_api_key_sm_exception_returns_none_and_warns(caplog):
    svc = CatalogService(FakeProviderRepo(), FakeModelRepo())
    provider = _provider_with_sm("projects/p/secrets/missing/versions/latest")

    fake_client = MagicMock()
    fake_client.access_secret_version.side_effect = RuntimeError("not found")

    with _install_fake_secretmanager(lambda: fake_client):
        with caplog.at_level(logging.WARNING, logger="gclaw.catalog.service"):
            result = svc.resolve_api_key(provider)

    assert result is None
    assert any(
        "Secret Manager access failed" in r.message for r in caplog.records
    )


def test_resolve_api_key_sm_missing_dep_returns_none(caplog):
    svc = CatalogService(FakeProviderRepo(), FakeModelRepo())
    provider = _provider_with_sm("projects/p/secrets/s/versions/latest")

    # Simulate ImportError by patching the import path.
    with patch.dict(sys.modules, {"google.cloud.secretmanager": None}):
        with caplog.at_level(logging.WARNING, logger="gclaw.catalog.service"):
            result = svc.resolve_api_key(provider)

    assert result is None
