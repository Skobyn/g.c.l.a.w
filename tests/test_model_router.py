"""Tests for model router."""

import pytest
from gclaw.models.model_config import ModelEndpoint, TaskProfile, RoutingRule
from gclaw.routing.router import ModelRouter


@pytest.fixture
def endpoints():
    return {
        "gemini-pro": ModelEndpoint(
            name="gemini-pro",
            endpoint_id="gemini-2.5-pro",
            max_context_tokens=1_000_000,
        ),
        "gemma-4-31b": ModelEndpoint(
            name="gemma-4-31b",
            endpoint_id="projects/test-project/locations/us-central1/endpoints/111",
            max_context_tokens=256_000,
        ),
        "nemotron-3-super": ModelEndpoint(
            name="nemotron-3-super",
            endpoint_id="projects/test-project/locations/us-central1/endpoints/222",
            max_context_tokens=1_000_000,
            provider="nim",
        ),
    }


@pytest.fixture
def rules():
    return [
        RoutingRule(task_profile=TaskProfile.ORCHESTRATION, model_name="gemini-pro"),
        RoutingRule(task_profile=TaskProfile.PERSONALITY, model_name="gemini-pro"),
        RoutingRule(task_profile=TaskProfile.TOOL_EXECUTION, model_name="nemotron-3-super"),
        RoutingRule(task_profile=TaskProfile.CODE_GENERATION, model_name="nemotron-3-super"),
        RoutingRule(task_profile=TaskProfile.SUMMARIZATION, model_name="gemma-4-31b"),
        RoutingRule(task_profile=TaskProfile.BACKGROUND, model_name="gemma-4-31b"),
    ]


@pytest.fixture
def router(endpoints, rules):
    return ModelRouter(
        endpoints=endpoints,
        rules=rules,
        default_model="gemini-2.5-flash",
    )


def test_resolve_orchestration(router):
    model_id = router.resolve(TaskProfile.ORCHESTRATION)
    assert model_id == "gemini-2.5-pro"


def test_resolve_tool_execution(router):
    model_id = router.resolve(TaskProfile.TOOL_EXECUTION)
    assert "222" in model_id


def test_resolve_summarization(router):
    model_id = router.resolve(TaskProfile.SUMMARIZATION)
    assert "111" in model_id


def test_resolve_unknown_profile_returns_default(router):
    router_no_rules = ModelRouter(
        endpoints={},
        rules=[],
        default_model="gemini-2.5-flash",
    )
    model_id = router_no_rules.resolve(TaskProfile.ORCHESTRATION)
    assert model_id == "gemini-2.5-flash"


def test_resolve_missing_endpoint_returns_default(router):
    bad_rules = [
        RoutingRule(task_profile=TaskProfile.ORCHESTRATION, model_name="nonexistent"),
    ]
    router_bad = ModelRouter(
        endpoints={},
        rules=bad_rules,
        default_model="gemini-2.5-flash",
    )
    model_id = router_bad.resolve(TaskProfile.ORCHESTRATION)
    assert model_id == "gemini-2.5-flash"


def test_resolve_by_agent_name(router):
    model_id = router.resolve_for_agent("orchestrator")
    assert model_id == "gemini-2.5-pro"


def test_resolve_by_agent_name_specialist(router):
    model_id = router.resolve_for_agent("code-specialist")
    assert "222" in model_id


def test_resolve_by_agent_name_unknown(router):
    model_id = router.resolve_for_agent("unknown-agent")
    assert model_id == "gemini-2.5-flash"


def test_get_endpoint_info(router):
    ep = router.get_endpoint(TaskProfile.ORCHESTRATION)
    assert ep is not None
    assert ep.name == "gemini-pro"
    assert ep.max_context_tokens == 1_000_000


def test_get_endpoint_info_missing(router):
    router_empty = ModelRouter(endpoints={}, rules=[], default_model="gemini-2.5-flash")
    ep = router_empty.get_endpoint(TaskProfile.ORCHESTRATION)
    assert ep is None
