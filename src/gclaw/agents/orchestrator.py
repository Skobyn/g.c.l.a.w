"""Orchestrator agent definition with board tools."""

from __future__ import annotations

from typing import Callable

from google.adk.agents import LlmAgent

from gclaw.agents.factory import AgentFactory
from gclaw.board.service import BoardService
from gclaw.models.task import TaskStatus


def create_board_task_tool(board_service: BoardService) -> Callable:
    def create_board_task(
        title: str,
        assignee: str,
        description: str = "",
        priority: str = "medium",
        source_origin: str = "orchestrator",
    ) -> str:
        """Create a task on the project board for a manager agent to pick up.

        Args:
            title: Short description of what needs to be done.
            assignee: Which manager agent should handle this. One of:
                workspace-mgr, dev-mgr, home-mgr, comms-mgr, research-mgr.
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


def build_orchestrator(
    factory: AgentFactory,
    board_service: BoardService,
    memories: list[str] | None = None,
) -> LlmAgent:
    """Build the root orchestrator agent with board tools."""
    tools = [
        create_board_task_tool(board_service),
        list_board_tasks_tool(board_service),
        get_board_task_tool(board_service),
    ]

    return factory.build(
        agent_name="orchestrator",
        tools=tools,
        memories=memories,
        description=(
            "Root orchestrator — classifies user intent and routes "
            "tasks to the appropriate manager agent via the project board."
        ),
    )
