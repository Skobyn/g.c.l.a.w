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
