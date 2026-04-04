"""Integration test: multi-provider routing with Gemini, Gemma, and OpenRouter."""

import pytest
from gclaw.config.loader import ConfigLoader
from gclaw.agents.factory import AgentFactory
from gclaw.models.model_config import ModelEndpoint, TaskProfile, RoutingRule
from gclaw.routing.router import ModelRouter


@pytest.fixture
def config_dir(tmp_path):
    soul_dir = tmp_path / "soul"
    soul_dir.mkdir()
    (soul_dir / "base.md").write_text("You are helpful.\n")
    (soul_dir / "workspace.md").write_text("Professional tone.\n")
    (soul_dir / "dev.md").write_text("Technical and precise.\n")

    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "orchestrator.md").write_text("Route to managers.\n")
    (agents_dir / "workspace-mgr.md").write_text("Manage workspace.\n")
    (agents_dir / "dev-mgr.md").write_text("Manage dev tasks.\n")
    return tmp_path


@pytest.fixture
def free_tier_router():
    endpoints = {
        "gemini-flash": ModelEndpoint(
            name="gemini-flash",
            endpoint_id="gemini-2.5-flash",
            provider="gemini",
            max_context_tokens=1_000_000,
        ),
        "gemma-4": ModelEndpoint(
            name="gemma-4",
            endpoint_id="gemma-4-26b-it",
            provider="gemini",
            max_context_tokens=256_000,
        ),
        "nemotron-3-super": ModelEndpoint(
            name="nemotron-3-super",
            endpoint_id="nvidia/nemotron-3-super-120b-a12b:free",
            provider="openrouter",
            api_base="https://openrouter.ai/api/v1",
            api_key_env="OPENROUTER_API_KEY",
            max_context_tokens=1_000_000,
        ),
    }
    rules = [
        RoutingRule(task_profile=TaskProfile.ORCHESTRATION, model_name="gemini-flash"),
        RoutingRule(task_profile=TaskProfile.PERSONALITY, model_name="gemini-flash"),
        RoutingRule(task_profile=TaskProfile.SUMMARIZATION, model_name="gemma-4"),
        RoutingRule(task_profile=TaskProfile.BACKGROUND, model_name="gemma-4"),
        RoutingRule(task_profile=TaskProfile.TOOL_EXECUTION, model_name="nemotron-3-super"),
        RoutingRule(task_profile=TaskProfile.CODE_GENERATION, model_name="nemotron-3-super"),
    ]
    return ModelRouter(endpoints=endpoints, rules=rules, default_model="gemini-2.5-flash")


def test_orchestrator_uses_gemini_flash(config_dir, free_tier_router):
    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(loader=loader, default_model="gemini-2.5-flash", model_router=free_tier_router)
    agent = factory.build(agent_name="orchestrator")
    assert agent.model == "gemini-2.5-flash"


def test_workspace_mgr_uses_gemma_4(config_dir, free_tier_router):
    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(loader=loader, default_model="gemini-2.5-flash", model_router=free_tier_router)
    agent = factory.build(agent_name="workspace-mgr", soul_overlay="workspace")
    assert agent.model == "gemma-4-26b-it"


def test_dev_mgr_uses_nemotron(config_dir, free_tier_router):
    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(loader=loader, default_model="gemini-2.5-flash", model_router=free_tier_router)
    agent = factory.build(agent_name="dev-mgr", soul_overlay="dev")
    assert agent.model == "nvidia/nemotron-3-super-120b-a12b:free"


def test_nemotron_endpoint_is_remote(free_tier_router):
    ep = free_tier_router.get_endpoint(TaskProfile.CODE_GENERATION)
    assert ep is not None
    assert ep.is_remote is True
    assert ep.api_base == "https://openrouter.ai/api/v1"


def test_gemma_endpoint_is_not_remote(free_tier_router):
    ep = free_tier_router.get_endpoint(TaskProfile.SUMMARIZATION)
    assert ep is not None
    assert ep.is_remote is False


def test_all_providers_accounted_for(free_tier_router):
    for profile in TaskProfile:
        model_id = free_tier_router.resolve(profile)
        assert model_id is not None
        assert model_id != ""
