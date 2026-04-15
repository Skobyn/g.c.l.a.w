"""Tests for the catalog pydantic models."""

from __future__ import annotations

from gclaw.models.catalog import (
    ApiKeyKind,
    ApiKeySpec,
    Capabilities,
    ModelCost,
    ModelParams,
    ModelProvider,
    ModelRecord,
    ProviderKind,
)


def test_provider_round_trip_literal_key():
    p = ModelProvider(
        name="My OpenAI",
        kind=ProviderKind.OPENAI,
        base_url="https://api.openai.com/v1",
        api_key=ApiKeySpec(kind=ApiKeyKind.LITERAL, value="sk-abc"),
    )
    d = p.to_firestore_dict()
    assert "id" not in d
    assert d["kind"] == "openai"
    assert d["api_key"]["kind"] == "literal"
    restored = ModelProvider.from_firestore_dict(p.id, d)
    assert restored.id == p.id
    assert restored.api_key.value == "sk-abc"
    assert restored.kind == ProviderKind.OPENAI


def test_provider_round_trip_env_key():
    p = ModelProvider(
        name="Env",
        kind=ProviderKind.ANTHROPIC,
        api_key=ApiKeySpec(kind=ApiKeyKind.ENV, value="ANTHROPIC_API_KEY"),
    )
    d = p.to_firestore_dict()
    restored = ModelProvider.from_firestore_dict(p.id, d)
    assert restored.api_key.kind == ApiKeyKind.ENV
    assert restored.api_key.value == "ANTHROPIC_API_KEY"


def test_provider_round_trip_anthropic_oauth():
    p = ModelProvider(
        name="Claude Code",
        kind=ProviderKind.ANTHROPIC_OAUTH,
        api_key=ApiKeySpec(kind=ApiKeyKind.LITERAL, value="sk-ant-oat-abc"),
    )
    d = p.to_firestore_dict()
    assert d["kind"] == "anthropic_oauth"
    restored = ModelProvider.from_firestore_dict(p.id, d)
    assert restored.kind == ProviderKind.ANTHROPIC_OAUTH
    assert restored.api_key.value == "sk-ant-oat-abc"


def test_provider_without_api_key():
    p = ModelProvider(name="Local", kind=ProviderKind.OLLAMA)
    d = p.to_firestore_dict()
    restored = ModelProvider.from_firestore_dict(p.id, d)
    assert restored.api_key is None


def test_model_round_trip_with_capabilities_and_cost():
    m = ModelRecord(
        provider_id="prov_x",
        model_id="gpt-4o",
        display_name="GPT-4o",
        context_window=128000,
        capabilities=Capabilities(vision=True, tools=True),
        params=ModelParams(temperature=0.7, max_tokens=1024),
        cost=ModelCost(input_per_mtok=2.5, output_per_mtok=10.0),
    )
    d = m.to_firestore_dict()
    assert "id" not in d
    restored = ModelRecord.from_firestore_dict(m.id, d)
    assert restored.id == m.id
    assert restored.capabilities.vision is True
    assert restored.params.temperature == 0.7
    assert restored.cost.input_per_mtok == 2.5


def test_legacy_model_dict_without_new_fields():
    # Simulate a doc written before some field was added
    data = {
        "provider_id": "prov_old",
        "model_id": "old-model",
        "display_name": "Old",
    }
    m = ModelRecord.from_firestore_dict("mdl_old", data)
    assert m.id == "mdl_old"
    assert m.enabled is True
    assert m.capabilities.text is True
    assert m.cost.input_per_mtok is None


def test_legacy_provider_dict_with_unknown_field():
    data = {
        "name": "X",
        "kind": "openai",
        "unknown_future_field": True,
    }
    p = ModelProvider.from_firestore_dict("prov_1", data)
    assert p.id == "prov_1"
    assert p.kind == ProviderKind.OPENAI
