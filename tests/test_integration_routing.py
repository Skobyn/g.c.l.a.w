"""Integration test: model routing from settings to agent creation."""

import os
import pytest
from gclaw.settings import Settings
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
def full_router():
    endpoints = {
        "gemini-pro": ModelEndpoint(
            name="gemini-pro",
            endpoint_id="gemini-2.5-pro",
            max_context_tokens=1_000_000,
        ),
        "gemma-4": ModelEndpoint(
            name="gemma-4",
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
    rules = [
        RoutingRule(task_profile=TaskProfile.ORCHESTRATION, model_name="gemini-pro"),
        RoutingRule(task_profile=TaskProfile.PERSONALITY, model_name="gemini-pro"),
        RoutingRule(task_profile=TaskProfile.TOOL_EXECUTION, model_name="nemotron-3-super"),
        RoutingRule(task_profile=TaskProfile.CODE_GENERATION, model_name="nemotron-3-super"),
        RoutingRule(task_profile=TaskProfile.SUMMARIZATION, model_name="gemma-4"),
        RoutingRule(task_profile=TaskProfile.BACKGROUND, model_name="gemma-4"),
    ]
    return ModelRouter(endpoints=endpoints, rules=rules, default_model="gemini-2.5-flash")


def test_orchestrator_gets_gemini(config_dir, full_router):
    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(loader=loader, default_model="gemini-2.5-flash", model_router=full_router)
    agent = factory.build(agent_name="orchestrator")
    assert agent.model == "gemini-2.5-pro"


def test_workspace_mgr_gets_gemma(config_dir, full_router):
    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(loader=loader, default_model="gemini-2.5-flash", model_router=full_router)
    agent = factory.build(agent_name="workspace-mgr", soul_overlay="workspace")
    # workspace-mgr → SUMMARIZATION → gemma-4 (provider="gemini" by default) → bare string
    assert isinstance(agent.model, str)
    assert "111" in agent.model


def test_dev_mgr_gets_nemotron(config_dir, full_router):
    from google.adk.models.lite_llm import LiteLlm

    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(loader=loader, default_model="gemini-2.5-flash", model_router=full_router)
    agent = factory.build(agent_name="dev-mgr", soul_overlay="dev")
    # dev-mgr → CODE_GENERATION → nemotron-3-super (provider="nim") → LiteLlm wrapped
    assert isinstance(agent.model, LiteLlm)
    assert "222" in agent.model.model


def test_unknown_agent_gets_default(config_dir, full_router):
    agents_dir = config_dir / "agents"
    (agents_dir / "generic.md").write_text("A generic agent.\n")

    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(loader=loader, default_model="gemini-2.5-flash", model_router=full_router)
    agent = factory.build(agent_name="generic")
    assert agent.model == "gemini-2.5-flash"


def test_explicit_model_overrides_routing(config_dir, full_router):
    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(loader=loader, default_model="gemini-2.5-flash", model_router=full_router)
    agent = factory.build(agent_name="orchestrator", model="custom-override")
    assert agent.model == "custom-override"


def test_routing_disabled_all_use_default(config_dir):
    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(loader=loader, default_model="gemini-2.5-flash")
    orchestrator = factory.build(agent_name="orchestrator")
    workspace = factory.build(agent_name="workspace-mgr", soul_overlay="workspace")
    assert orchestrator.model == "gemini-2.5-flash"
    assert workspace.model == "gemini-2.5-flash"
