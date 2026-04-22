"""Tests for model routing settings."""

import os
import pytest
from gclaw.settings import Settings


_ROUTING_ENV_VARS = [
    "MODEL_ROUTING_ENABLED",
    "GEMMA_ENDPOINT_ID",
    "NEMOTRON_ENDPOINT_ID",
    "NEMOTRON_PROVIDER",
    "OPENROUTER_API_KEY",
]


@pytest.fixture
def clean_routing_env(monkeypatch):
    """Clear routing-related env vars leaked in from .env."""
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
    for key in _ROUTING_ENV_VARS:
        monkeypatch.delenv(key, raising=False)


def test_settings_model_routing_defaults(clean_routing_env):
    s = Settings()
    assert s.model_routing_enabled is False
    assert s.gemma_endpoint_id == ""
    assert s.nemotron_endpoint_id == ""
    assert s.nemotron_provider == "vertex"


def test_settings_model_routing_enabled(clean_routing_env, monkeypatch):
    monkeypatch.setenv("MODEL_ROUTING_ENABLED", "true")
    monkeypatch.setenv(
        "GEMMA_ENDPOINT_ID",
        "projects/test-project/locations/us-central1/endpoints/111",
    )
    monkeypatch.setenv(
        "NEMOTRON_ENDPOINT_ID",
        "projects/test-project/locations/us-central1/endpoints/222",
    )
    monkeypatch.setenv("NEMOTRON_PROVIDER", "nim")
    s = Settings()
    assert s.model_routing_enabled is True
    assert "111" in s.gemma_endpoint_id
    assert "222" in s.nemotron_endpoint_id
    assert s.nemotron_provider == "nim"


def test_settings_openrouter_api_key_default(clean_routing_env):
    s = Settings()
    assert s.openrouter_api_key == ""


def test_settings_openrouter_api_key_set(clean_routing_env, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-123")
    s = Settings()
    assert s.openrouter_api_key == "sk-or-test-123"
