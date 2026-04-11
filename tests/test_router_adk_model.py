"""Tests for ModelRouter's ADK-ready model builders."""

from unittest.mock import patch

import pytest

from gclaw.models.model_config import ModelEndpoint, RoutingRule, TaskProfile
from gclaw.routing.router import ModelRouter


@pytest.fixture
def router():
    endpoints = {
        "gemini-flash": ModelEndpoint(
            name="gemini-flash",
            endpoint_id="gemini-2.5-flash",
            provider="gemini",
        ),
        "gemma-4": ModelEndpoint(
            name="gemma-4",
            endpoint_id="gemma-4-26b-it",
            provider="gemini",
        ),
        "nemotron-3-super": ModelEndpoint(
            name="nemotron-3-super",
            endpoint_id="nvidia/nemotron-3-super-120b-a12b:free",
            provider="openrouter",
        ),
    }
    rules = [
        RoutingRule(task_profile=TaskProfile.ORCHESTRATION, model_name="gemini-flash"),
        RoutingRule(task_profile=TaskProfile.SUMMARIZATION, model_name="gemma-4"),
        RoutingRule(task_profile=TaskProfile.CODE_GENERATION, model_name="nemotron-3-super"),
    ]
    return ModelRouter(endpoints=endpoints, rules=rules, default_model="gemini-2.5-flash")


def test_build_adk_model_for_profile_gemini_returns_string(router):
    result = router.build_adk_model_for_profile(TaskProfile.ORCHESTRATION)
    assert result == "gemini-2.5-flash"


def test_build_adk_model_for_profile_gemma_returns_string(router):
    result = router.build_adk_model_for_profile(TaskProfile.SUMMARIZATION)
    assert result == "gemma-4-26b-it"


def test_build_adk_model_for_profile_openrouter_returns_litellm(router):
    from google.adk.models.lite_llm import LiteLlm

    result = router.build_adk_model_for_profile(TaskProfile.CODE_GENERATION)
    assert isinstance(result, LiteLlm)
    assert "nemotron" in result.model.lower()
    assert result.model.startswith("openrouter/")


def test_build_adk_model_for_profile_unknown_returns_default(router):
    result = router.build_adk_model_for_profile(TaskProfile.PERSONALITY)
    assert result == "gemini-2.5-flash"


def test_build_adk_model_for_agent_orchestrator(router):
    result = router.build_adk_model_for_agent("orchestrator")
    assert result == "gemini-2.5-flash"


def test_build_adk_model_for_agent_dev_mgr_returns_litellm(router):
    from google.adk.models.lite_llm import LiteLlm

    result = router.build_adk_model_for_agent("dev-mgr")
    assert isinstance(result, LiteLlm)


def test_build_adk_model_for_agent_unknown_returns_default(router):
    result = router.build_adk_model_for_agent("nonexistent-mgr")
    assert result == "gemini-2.5-flash"


def test_build_adk_model_for_agent_suffix_match(router):
    result = router.build_adk_model_for_agent("some-code-specialist")
    from google.adk.models.lite_llm import LiteLlm

    assert isinstance(result, LiteLlm)
