"""Tests for agent factory."""

import pytest
from gclaw.agents.factory import AgentFactory
from gclaw.config.loader import ConfigLoader


@pytest.fixture
def config_dir(tmp_path):
    soul_dir = tmp_path / "soul"
    soul_dir.mkdir()
    (soul_dir / "base.md").write_text("You are helpful.\n")
    (soul_dir / "workspace.md").write_text("Professional email tone.\n")

    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "orchestrator.md").write_text(
        "You are the root orchestrator. Route to managers.\n"
    )
    (agents_dir / "workspace-mgr.md").write_text(
        "You manage workspace tasks.\n"
    )
    return tmp_path


@pytest.fixture
def factory(config_dir):
    loader = ConfigLoader(str(config_dir))
    return AgentFactory(loader=loader, default_model="gemini-2.5-flash")


def test_build_agent(factory):
    agent = factory.build(
        agent_name="orchestrator",
        soul_overlay=None,
    )
    assert agent.name == "orchestrator"
    assert "root orchestrator" in agent.instruction
    assert "helpful" in agent.instruction


def test_build_agent_with_overlay(factory):
    agent = factory.build(
        agent_name="workspace-mgr",
        soul_overlay="workspace",
    )
    assert agent.name == "workspace_mgr"
    assert "Professional email" in agent.instruction
    assert "helpful" in agent.instruction


def test_build_agent_with_tools(factory):
    def dummy_tool(x: str) -> str:
        """A dummy tool."""
        return x

    agent = factory.build(
        agent_name="orchestrator",
        tools=[dummy_tool],
    )
    assert len(agent.tools) == 1


def test_build_agent_with_sub_agents(factory):
    child = factory.build(agent_name="workspace-mgr", soul_overlay="workspace")
    parent = factory.build(
        agent_name="orchestrator",
        sub_agents=[child],
    )
    assert len(parent.sub_agents) == 1
    assert parent.sub_agents[0].name == "workspace_mgr"


def test_build_agent_with_memories(factory):
    agent = factory.build(
        agent_name="orchestrator",
        memories=["User likes bullet points."],
    )
    assert "bullet points" in agent.instruction


from unittest.mock import MagicMock
from gclaw.models.model_config import ModelEndpoint, TaskProfile, RoutingRule
from gclaw.routing.router import ModelRouter


@pytest.fixture
def model_router():
    endpoints = {
        "gemini-pro": ModelEndpoint(
            name="gemini-pro",
            endpoint_id="gemini-2.5-pro",
            max_context_tokens=1_000_000,
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
        RoutingRule(task_profile=TaskProfile.CODE_GENERATION, model_name="nemotron-3-super"),
    ]
    return ModelRouter(endpoints=endpoints, rules=rules, default_model="gemini-2.5-flash")


def test_build_agent_with_router(config_dir, model_router):
    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(
        loader=loader,
        default_model="gemini-2.5-flash",
        model_router=model_router,
    )
    agent = factory.build(agent_name="orchestrator")
    assert agent.model == "gemini-2.5-pro"


def test_build_agent_explicit_model_overrides_router(config_dir, model_router):
    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(
        loader=loader,
        default_model="gemini-2.5-flash",
        model_router=model_router,
    )
    agent = factory.build(agent_name="orchestrator", model="custom-model-id")
    assert agent.model == "custom-model-id"


def test_build_agent_without_router_uses_default(config_dir):
    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(loader=loader, default_model="gemini-2.5-flash")
    agent = factory.build(agent_name="orchestrator")
    assert agent.model == "gemini-2.5-flash"
