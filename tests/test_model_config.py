"""Tests for model configuration models."""

from gclaw.models.model_config import ModelEndpoint, TaskProfile, RoutingRule


def test_model_endpoint_defaults():
    ep = ModelEndpoint(
        name="gemma-4-31b",
        endpoint_id="projects/apexfoundation/locations/us-central1/endpoints/123",
    )
    assert ep.name == "gemma-4-31b"
    assert ep.provider == "gemini"
    assert ep.max_context_tokens == 0


def test_model_endpoint_with_context():
    ep = ModelEndpoint(
        name="nemotron-3-super",
        endpoint_id="projects/apexfoundation/locations/us-central1/endpoints/456",
        max_context_tokens=1_000_000,
        provider="nim",
    )
    assert ep.max_context_tokens == 1_000_000
    assert ep.provider == "nim"


def test_task_profile_values():
    assert TaskProfile.ORCHESTRATION == "orchestration"
    assert TaskProfile.TOOL_EXECUTION == "tool_execution"
    assert TaskProfile.CODE_GENERATION == "code_generation"
    assert TaskProfile.SUMMARIZATION == "summarization"
    assert TaskProfile.PERSONALITY == "personality"
    assert TaskProfile.BACKGROUND == "background"


def test_routing_rule():
    rule = RoutingRule(
        task_profile=TaskProfile.TOOL_EXECUTION,
        model_name="nemotron-3-super",
    )
    assert rule.task_profile == TaskProfile.TOOL_EXECUTION
    assert rule.model_name == "nemotron-3-super"


def test_model_endpoint_with_api_base():
    ep = ModelEndpoint(
        name="nemotron-3-super",
        endpoint_id="nvidia/nemotron-3-super-120b-a12b:free",
        provider="openrouter",
        api_base="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        max_context_tokens=1_000_000,
    )
    assert ep.api_base == "https://openrouter.ai/api/v1"
    assert ep.api_key_env == "OPENROUTER_API_KEY"
    assert ep.provider == "openrouter"


def test_model_endpoint_gemini_api_defaults():
    ep = ModelEndpoint(
        name="gemma-4-26b",
        endpoint_id="gemma-4-26b-it",
        provider="gemini",
    )
    assert ep.api_base is None
    assert ep.api_key_env is None


def test_model_endpoint_is_remote():
    remote = ModelEndpoint(
        name="nemotron",
        endpoint_id="nvidia/nemotron-3-super-120b-a12b:free",
        provider="openrouter",
        api_base="https://openrouter.ai/api/v1",
    )
    local = ModelEndpoint(
        name="gemma",
        endpoint_id="gemma-4-26b-it",
        provider="gemini",
    )
    assert remote.is_remote is True
    assert local.is_remote is False
