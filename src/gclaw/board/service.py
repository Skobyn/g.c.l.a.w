"""Board service — business logic for kanban task management."""

from __future__ import annotations

from gclaw.firestore.board_repo import BoardRepo
from gclaw.models.task import (
    BoardTask,
    TaskPriority,
    TaskResult,
    TaskSource,
    TaskSourceType,
    TaskStatus,
)


class BoardService:
    """High-level operations on the project board."""

    def __init__(self, repo: BoardRepo) -> None:
        self._repo = repo

    def create_task(
        self,
        title: str,
        assignee: str,
        source_type: str = "user",
        source_origin: str | None = None,
        description: str = "",
        priority: TaskPriority = TaskPriority.MEDIUM,
        status: TaskStatus = TaskStatus.BACKLOG,
        dependencies: list[str] | None = None,
        requires_approval: bool = False,
    ) -> BoardTask:
        task = BoardTask(
            title=title,
            description=description,
            status=status,
            priority=priority,
            source=TaskSource(
                type=TaskSourceType(source_type),
                origin=source_origin,
            ),
            assignee=assignee,
            dependencies=dependencies or [],
            requires_approval=requires_approval,
        )
        return self._repo.create(task)

    def pick_up(self, task_id: str) -> BoardTask:
        task = self._repo.get(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        updated = task.transition_to(TaskStatus.IN_PROGRESS)
        return self._repo.update(updated)

    def complete(
        self,
        task_id: str,
        summary: str,
        artifacts: list[str] | None = None,
    ) -> BoardTask:
        task = self._repo.get(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        completed = task.complete(TaskResult(
            summary=summary, artifacts=artifacts or []
        ))
        return self._repo.update(completed)

    def fail(self, task_id: str, reason: str) -> BoardTask:
        task = self._repo.get(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        failed = task.transition_to(TaskStatus.FAILED)
        failed = failed.model_copy(
            update={"result": TaskResult(summary=reason)}
        )
        return self._repo.update(failed)

    def get_pending_tasks(self, assignee: str) -> list[BoardTask]:
        return self._repo.list_by_assignee(assignee, status=TaskStatus.QUEUED)

    def get_all_tasks(self) -> list[BoardTask]:
        return self._repo.list_all()
