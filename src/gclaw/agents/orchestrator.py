"""Root orchestrator agent with AgentTool-wrapped managers and workflows."""

from __future__ import annotations

from typing import Any, Callable

from google.adk.agents import LlmAgent
from google.adk.tools import agent_tool

from gclaw.agents.factory import AgentFactory
from gclaw.agents.workflows.morning_brief import build_morning_brief
from gclaw.agents.workflows.commit_message import build_commit_message_workflow
from gclaw.board.service import BoardService
from gclaw.models.task import TaskStatus
from gclaw.routing.router import ModelRouter
from gclaw.tools import (
    comms_tools,
    dev_tools,
    home_tools,
    research_tools,
    workspace_tools,
)


# ---------- Board function tools ----------


def create_board_task_tool(board_service: BoardService) -> Callable:
    def create_board_task(
        title: str,
        assignee: str,
        description: str = "",
        priority: str = "medium",
        source_origin: str = "orchestrator",
    ) -> str:
        """Create an async task on the project board for a manager to pick up later.

        Args:
            title: Short description of what needs to be done.
            assignee: Which manager should handle this.
                One of: workspace-mgr, dev-mgr, home-mgr, comms-mgr, research-mgr.
            description: Detailed context for the assigned agent.
            priority: Task priority — high, medium, or low.
            source_origin: Which agent created this task.

        Returns:
            Confirmation with the created task ID and details.
        """
        task = board_service.create_task(
            title=title,
            assignee=assignee,
            description=description,
            priority=priority,
            source_type="agent",
            source_origin=source_origin,
            status=TaskStatus.QUEUED,
        )
        return (
            f"Task created: [{task.id}] '{task.title}' "
            f"assigned to {task.assignee} (priority: {task.priority})"
        )

    return create_board_task


def list_board_tasks_tool(board_service: BoardService) -> Callable:
    def list_board_tasks() -> str:
        """List all tasks currently on the project board.

        Returns:
            A formatted list of all board tasks with their status.
        """
        tasks = board_service.get_all_tasks()
        if not tasks:
            return "The board is empty — no tasks."
        lines = []
        for t in tasks:
            lines.append(
                f"- [{t.id}] {t.title} | status: {t.status} | "
                f"assignee: {t.assignee} | priority: {t.priority}"
            )
        return "\n".join(lines)

    return list_board_tasks


def get_board_task_tool(board_service: BoardService) -> Callable:
    def get_board_task(task_id: str) -> str:
        """Get details of a specific board task by ID.

        Args:
            task_id: The task ID to look up.

        Returns:
            Full task details or a not-found message.
        """
        task = board_service._repo.get(task_id)
        if task is None:
            return f"Task {task_id} not found."
        parts = [
            f"Task: {task.title}",
            f"ID: {task.id}",
            f"Status: {task.status}",
            f"Assignee: {task.assignee}",
            f"Priority: {task.priority}",
            f"Description: {task.description or '(none)'}",
            f"Source: {task.source.type} / {task.source.origin or 'user'}",
            f"Dependencies: {task.dependencies or '(none)'}",
            f"Requires approval: {task.requires_approval}",
        ]
        if task.result:
            parts.append(f"Result: {task.result.summary}")
        return "\n".join(parts)

    return get_board_task


def complete_board_task_tool(board_service: BoardService) -> Callable:
    def complete_board_task(task_id: str, summary: str = "") -> str:
        """Mark a board task as complete.

        Args:
            task_id: The task ID to complete.
            summary: Brief summary of what was done.

        Returns:
            Confirmation message.
        """
        task = board_service.complete(task_id=task_id, summary=summary)
        if task is None:
            return f"Task {task_id} not found."
        return f"Task [{task.id}] '{task.title}' marked as DONE."

    return complete_board_task


# ---------- Manager builders ----------


def build_managers(
    factory: AgentFactory, board_tools: list
) -> dict[str, LlmAgent]:
    """Build the five manager agents as thin routers.

    Each manager is bound to its own domain tools plus the shared board tools
    (so it can create follow-up async tasks for work it cannot finish now).
    """
    ws_tools = [
        workspace_tools.list_unread_email,
        workspace_tools.send_email,
        workspace_tools.list_calendar_events_today,
        workspace_tools.create_calendar_event,
        workspace_tools.list_drive_files,
        workspace_tools.read_drive_doc,
    ] + board_tools

    dv_tools = [
        dev_tools.list_open_prs,
        dev_tools.get_pr_diff,
        dev_tools.list_failing_workflows,
        dev_tools.create_issue,
        dev_tools.get_current_diff,
        dev_tools.read_local_file,
    ] + board_tools

    hm_tools = [
        home_tools.list_devices,
        home_tools.set_device_state,
    ] + board_tools

    cm_tools = [
        comms_tools.list_chat_spaces,
        comms_tools.post_chat_message,
    ] + board_tools

    rs_tools = [
        research_tools.web_search,
        research_tools.fetch_url,
    ] + board_tools

    return {
        "workspace_mgr": factory.build(
            agent_name="workspace-mgr",
            soul_overlay="workspace",
            tools=ws_tools,
            description=(
                "Routes workspace requests (Gmail, Calendar, Drive, Docs) "
                "to the single best tool. Router — does not synthesize."
            ),
        ),
        "dev_mgr": factory.build(
            agent_name="dev-mgr",
            soul_overlay="dev",
            tools=dv_tools,
            description=(
                "Routes dev requests (GitHub, code, local repo) to the "
                "single best tool. Router — does not synthesize."
            ),
        ),
        "home_mgr": factory.build(
            agent_name="home-mgr",
            soul_overlay="home",
            tools=hm_tools,
            description=(
                "Routes smart home requests to the single best tool. "
                "Router — does not synthesize."
            ),
        ),
        "comms_mgr": factory.build(
            agent_name="comms-mgr",
            soul_overlay="comms",
            tools=cm_tools,
            description=(
                "Routes inter-platform comms (Google Chat) to the single "
                "best tool. Router — does not synthesize."
            ),
        ),
        "research_mgr": factory.build(
            agent_name="research-mgr",
            soul_overlay="research",
            tools=rs_tools,
            description=(
                "Routes research requests (web search, URL fetch) to the "
                "single best tool. Router — does not synthesize."
            ),
        ),
    }


# ---------- Orchestrator builder ----------


def build_orchestrator(
    factory: AgentFactory,
    board_service: BoardService,
    router: ModelRouter | None = None,
    default_model: str = "gemini-2.5-flash",
    memories: list[str] | None = None,
) -> LlmAgent:
    """Build the root orchestrator with AgentTool-wrapped managers and workflows.

    Args:
        factory: the AgentFactory used to build named agents from config files.
        board_service: the board service used to create/list/get/complete tasks.
        router: the ModelRouter — needed by workflows that construct raw LlmAgents.
        default_model: fallback model ID used when the router is absent.
        memories: optional memory facts to prepend to the system prompt.

    Returns:
        The root orchestrator LlmAgent, wired with all managers and workflows
        as AgentTools plus the board function tools. Never uses `sub_agents=`.
    """
    board_tools = [
        create_board_task_tool(board_service),
        list_board_tasks_tool(board_service),
        get_board_task_tool(board_service),
        complete_board_task_tool(board_service),
    ]

    managers = build_managers(factory, board_tools)

    morning_brief = build_morning_brief(
        workspace_tools=[
            workspace_tools.list_unread_email,
            workspace_tools.list_calendar_events_today,
        ],
        dev_tools=[
            dev_tools.list_open_prs,
            dev_tools.list_failing_workflows,
        ],
        research_tools=[research_tools.web_search],
        default_model=default_model,
    )

    commit_msg = build_commit_message_workflow(
        dev_tools=[
            dev_tools.get_current_diff,
            dev_tools.read_local_file,
        ],
        router=router,
        default_model=default_model,
    )

    orchestrator_tools: list[Any] = [
        agent_tool.AgentTool(agent=managers["workspace_mgr"]),
        agent_tool.AgentTool(agent=managers["dev_mgr"]),
        agent_tool.AgentTool(agent=managers["home_mgr"]),
        agent_tool.AgentTool(agent=managers["comms_mgr"]),
        agent_tool.AgentTool(agent=managers["research_mgr"]),
        agent_tool.AgentTool(agent=morning_brief),
        agent_tool.AgentTool(agent=commit_msg),
        *board_tools,
    ]

    return factory.build(
        agent_name="orchestrator",
        tools=orchestrator_tools,
        memories=memories,
        description=(
            "Root orchestrator. Classifies user intent and delegates to the "
            "right manager or composed workflow. Never does work directly."
        ),
    )
