"""Integration test: orchestrator delegates via AgentTool, never sub_agents.

This is the regression guard against the 'receptionist' anti-pattern the
Google ADK team critiques: LlmAgent(sub_agents=[...]) transfers full control
to a sub-agent and cannot orchestrate multi-step workflows.

The refactor replaces sub_agents with agent_tool.AgentTool(...) so the root
stays in control between delegations.
"""

from unittest.mock import MagicMock

import pytest
from google.adk.tools import agent_tool

from gclaw.agents.factory import AgentFactory
from gclaw.agents.orchestrator import build_orchestrator
from gclaw.board.service import BoardService
from gclaw.config.loader import ConfigLoader


@pytest.fixture
def tmp_config_dir(tmp_path):
    soul = tmp_path / "soul"
    soul.mkdir()
    (soul / "base.md").write_text("Base personality.\n")
    (soul / "workspace.md").write_text("Workspace overlay.\n")
    (soul / "dev.md").write_text("Dev overlay.\n")
    (soul / "home.md").write_text("Home overlay.\n")
    (soul / "comms.md").write_text("Comms overlay.\n")
    (soul / "research.md").write_text("Research overlay.\n")
    (soul / "profile.md").write_text("Profile overlay.\n")

    agents = tmp_path / "agents"
    agents.mkdir()
    for name in (
        "orchestrator",
        "workspace-mgr",
        "dev-mgr",
        "home-mgr",
        "comms-mgr",
        "research-mgr",
        "profile-mgr",
    ):
        (agents / f"{name}.md").write_text(f"{name} role description.\n")

    return tmp_path


@pytest.fixture
def orchestrator(tmp_config_dir):
    loader = ConfigLoader(str(tmp_config_dir))
    factory = AgentFactory(
        loader=loader, default_model="gemini-2.5-flash", model_router=None
    )
    bs = MagicMock(spec=BoardService)
    return build_orchestrator(
        factory=factory,
        board_service=bs,
        router=None,
        default_model="gemini-2.5-flash",
    )


def test_orchestrator_has_no_sub_agents(orchestrator):
    """Critical: orchestrator must NOT use sub_agents. AgentTool only."""
    assert not orchestrator.sub_agents, (
        "Orchestrator uses sub_agents=[...] — that's the 'receptionist' "
        "anti-pattern. Use agent_tool.AgentTool(...) instead."
    )


def test_orchestrator_wraps_all_five_managers_as_agenttools(orchestrator):
    agent_tool_instances = [
        t for t in orchestrator.tools if isinstance(t, agent_tool.AgentTool)
    ]
    tool_agent_names = {t.agent.name for t in agent_tool_instances}

    expected_managers = {
        "workspace_mgr",
        "dev_mgr",
        "home_mgr",
        "comms_mgr",
        "research_mgr",
        "profile_mgr",
    }
    assert expected_managers.issubset(tool_agent_names), (
        f"Missing manager AgentTools. Got: {tool_agent_names}"
    )


def test_orchestrator_wraps_both_workflows_as_agenttools(orchestrator):
    agent_tool_instances = [
        t for t in orchestrator.tools if isinstance(t, agent_tool.AgentTool)
    ]
    workflow_names = {t.agent.name for t in agent_tool_instances}
    assert "MorningBriefWorkflow" in workflow_names
    assert "CommitMessageWorkflow" in workflow_names


def test_orchestrator_has_board_function_tools(orchestrator):
    """Board tools remain as plain function tools (not AgentTools)."""
    function_tools = [
        t for t in orchestrator.tools if callable(t) and not isinstance(t, agent_tool.AgentTool)
    ]
    function_names = {getattr(t, "__name__", None) for t in function_tools}
    assert "create_board_task" in function_names
    assert "list_board_tasks" in function_names
    assert "get_board_task" in function_names
    assert "complete_board_task" in function_names


def test_managers_are_thin_routers_without_nested_sub_agents(orchestrator):
    """Each manager's sub_agents list must also be empty — managers route, not compose."""
    manager_tools = [
        t for t in orchestrator.tools
        if isinstance(t, agent_tool.AgentTool)
        and t.agent.name.endswith("_mgr")
    ]
    for t in manager_tools:
        assert not t.agent.sub_agents, (
            f"{t.agent.name} has sub_agents — managers must be flat routers."
        )


def test_workflow_specialists_are_private_to_their_workflow(orchestrator):
    """Workflow specialists must not appear directly in the orchestrator's tools."""
    agent_tool_instances = [
        t for t in orchestrator.tools if isinstance(t, agent_tool.AgentTool)
    ]
    direct_targets = {t.agent.name for t in agent_tool_instances}

    forbidden_direct = {
        "workspace_brief_specialist",
        "dev_brief_specialist",
        "research_brief_specialist",
        "brief_summary_agent",
        "commit_draft_specialist",
        "style_reviewer_specialist",
        "validate_commit_msg",
    }
    leaked = forbidden_direct & direct_targets
    assert not leaked, f"Workflow specialists leaked to orchestrator tools: {leaked}"
