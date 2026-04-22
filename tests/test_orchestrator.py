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


def test_get_board_task_tool_does_not_pickup_when_caller_is_not_assignee(
    board_service,
):
    """A non-assignee reading a QUEUED task must NOT auto-pickup.

    Regression: previously any caller reading a QUEUED task flipped it
    to IN_PROGRESS via the side-effect in ``board_service.pick_up``, so
    a passing inspection by the orchestrator or another manager would
    orphan the task (the real assignee would never see it as queued).
    """
    task = BoardTask(
        id="t1", title="Research", assignee="research-mgr",
        status=TaskStatus.QUEUED,
    )
    repo_mock = MagicMock()
    repo_mock.get.return_value = task
    board_service._repo = repo_mock

    tool_fn = get_board_task_tool(board_service)

    # Simulate ADK injecting a ToolContext from the *orchestrator* (not
    # the research-mgr assignee). We just need `.agent_name` — a bare
    # MagicMock with the attribute set is sufficient.
    fake_context = MagicMock()
    fake_context.agent_name = "orchestrator"

    result = tool_fn(task_id="t1", tool_context=fake_context)
    assert "Research" in result
    board_service.pick_up.assert_not_called()


def test_get_board_task_tool_picks_up_when_caller_is_assignee(board_service):
    task = BoardTask(
        id="t1", title="Research", assignee="research-mgr",
        status=TaskStatus.QUEUED,
    )
    repo_mock = MagicMock()
    repo_mock.get.return_value = task
    board_service._repo = repo_mock
    # pick_up returns the transitioned task
    board_service.pick_up.return_value = task.model_copy(
        update={"status": TaskStatus.IN_PROGRESS}
    )

    tool_fn = get_board_task_tool(board_service)
    fake_context = MagicMock()
    fake_context.agent_name = "research-mgr"

    tool_fn(task_id="t1", tool_context=fake_context)
    board_service.pick_up.assert_called_once_with("t1")


def test_get_board_task_tool_picks_up_with_underscore_variant(board_service):
    """ADK normalizes agent names to `foo_bar`; the task assignee is
    stored as `foo-bar`. The gate must treat them as equal."""
    task = BoardTask(
        id="t1", title="Research", assignee="research-mgr",
        status=TaskStatus.QUEUED,
    )
    repo_mock = MagicMock()
    repo_mock.get.return_value = task
    board_service._repo = repo_mock
    board_service.pick_up.return_value = task.model_copy(
        update={"status": TaskStatus.IN_PROGRESS}
    )

    tool_fn = get_board_task_tool(board_service)
    fake_context = MagicMock()
    fake_context.agent_name = "research_mgr"  # ADK-safe form

    tool_fn(task_id="t1", tool_context=fake_context)
    board_service.pick_up.assert_called_once_with("t1")


def test_get_board_task_tool_type_hints_resolve(board_service):
    """Regression: the tool's annotations must be resolvable at runtime.

    With ``from __future__ import annotations`` at the top of the module
    (standard in this codebase), every annotation is deferred to a
    string. If any annotation references a name that's only imported
    under ``if TYPE_CHECKING:``, ``typing.get_type_hints`` blows up with
    NameError — which in turn breaks ADK FunctionTool registration and
    every downstream caller (AgentTool wrapping, model tests, chat).

    PR #31 regressed this by annotating ``tool_context`` as
    ``"ToolContext | None"`` with the import behind TYPE_CHECKING, which
    broke all non-Gemini model calls in production (the model.test
    endpoint was the first place the failure surfaced).
    """
    import typing

    tool = get_board_task_tool(board_service)
    # MUST NOT raise.
    hints = typing.get_type_hints(tool)
    assert "task_id" in hints
    assert "tool_context" in hints


def test_get_board_task_tool_no_context_skips_pickup(board_service):
    """Without a ToolContext (e.g. direct Python caller), we don't know
    the assignee, so pickup is skipped — the safer default."""
    task = BoardTask(
        id="t1", title="Research", assignee="research-mgr",
        status=TaskStatus.QUEUED,
    )
    repo_mock = MagicMock()
    repo_mock.get.return_value = task
    board_service._repo = repo_mock

    tool_fn = get_board_task_tool(board_service)
    tool_fn(task_id="t1")  # no tool_context
    board_service.pick_up.assert_not_called()


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
        "profile-mgr",
        "content-mgr",
    ]:
        (agents_dir / f"{name}.md").write_text(f"You are {name}.\n")

    from gclaw.config.loader import ConfigLoader
    from gclaw.agents.factory import AgentFactory

    loader = ConfigLoader(str(tmp_path))
    factory = AgentFactory(loader=loader)

    agent = build_orchestrator(factory=factory, board_service=board_service)
    assert agent.name == "orchestrator"

    # New shape: 7 manager AgentTools + 2 workflow AgentTools
    # + 4 board tools + 1 user-profile tool = 14
    assert len(agent.tools) >= 14
    # Core invariant: orchestrator never uses sub_agents
    assert not agent.sub_agents
    # All managers and workflows are wrapped as AgentTools
    agent_tools = [t for t in agent.tools if isinstance(t, agent_tool.AgentTool)]
    assert len(agent_tools) == 9  # 7 managers + 2 workflows
