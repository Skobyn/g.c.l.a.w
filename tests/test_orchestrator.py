"""Tests for orchestrator agent tools."""

import pytest
from unittest.mock import MagicMock

from google.adk.tools import agent_tool

from gclaw.agents.orchestrator import (
    create_board_task_tool,
    list_board_tasks_tool,
    get_board_task_tool,
    build_orchestrator,
)
from gclaw.board.service import BoardService
from gclaw.models.task import BoardTask, TaskStatus


@pytest.fixture
def board_service():
    return MagicMock(spec=BoardService)


def test_create_board_task_tool(board_service):
    board_service.create_task.side_effect = lambda **kw: BoardTask(
        title=kw["title"], assignee=kw["assignee"]
    )
    tool_fn = create_board_task_tool(board_service)
    result = tool_fn(
        title="Send email to Sarah",
        assignee="workspace-mgr",
        description="Draft and send meeting follow-up",
        priority="high",
    )
    assert "Send email to Sarah" in result
    board_service.create_task.assert_called_once()


def test_list_board_tasks_tool(board_service):
    board_service.get_all_tasks.return_value = [
        BoardTask(id="t1", title="Task 1", assignee="dev-mgr", status=TaskStatus.QUEUED),
        BoardTask(id="t2", title="Task 2", assignee="workspace-mgr", status=TaskStatus.DONE),
    ]
    tool_fn = list_board_tasks_tool(board_service)
    result = tool_fn()
    assert "Task 1" in result
    assert "Task 2" in result


def test_get_board_task_tool(board_service):
    task = BoardTask(id="t1", title="Specific task", assignee="dev-mgr", status=TaskStatus.IN_PROGRESS)
    repo_mock = MagicMock()
    repo_mock.get.return_value = task
    board_service._repo = repo_mock

    tool_fn = get_board_task_tool(board_service)
    result = tool_fn(task_id="t1")
    assert "Specific task" in result


def test_build_orchestrator(board_service, tmp_path):
    soul_dir = tmp_path / "soul"
    soul_dir.mkdir()
    (soul_dir / "base.md").write_text("You are helpful.\n")
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    # Scaffold all agent config files required by the new orchestrator
    for name in [
        "orchestrator",
        "workspace-mgr",
        "dev-mgr",
        "home-mgr",
        "comms-mgr",
        "research-mgr",
    ]:
        (agents_dir / f"{name}.md").write_text(f"You are {name}.\n")

    from gclaw.config.loader import ConfigLoader
    from gclaw.agents.factory import AgentFactory

    loader = ConfigLoader(str(tmp_path))
    factory = AgentFactory(loader=loader)

    agent = build_orchestrator(factory=factory, board_service=board_service)
    assert agent.name == "orchestrator"

    # New shape: 5 manager AgentTools + 2 workflow AgentTools + 4 board tools = 11
    assert len(agent.tools) >= 11
    # Core invariant: orchestrator never uses sub_agents
    assert not agent.sub_agents
    # All managers and workflows are wrapped as AgentTools
    agent_tools = [t for t in agent.tools if isinstance(t, agent_tool.AgentTool)]
    assert len(agent_tools) == 7  # 5 managers + 2 workflows
