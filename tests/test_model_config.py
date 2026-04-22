"""Tests for model configuration models."""

from gclaw.models.model_config import ModelEndpoint, TaskProfile, RoutingRule


def test_model_endpoint_defaults():
    ep = ModelEndpoint(
        name="gemma-4-31b",
        endpoint_id="projects/test-project/locations/us-central1/endpoints/123",
    )
    assert ep.name == "gemma-4-31b"
    assert ep.provider == "gemini"
    assert ep.max_context_tokens == 0


def test_model_endpoint_with_context():
    ep = ModelEndpoint(
        name="nemotron-3-super",
        endpoint_id="projects/test-project/locations/us-central1/endpoints/456",
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
