"""Board service — business logic for kanban task management."""

from __future__ import annotations

from datetime import datetime, timezone

from gclaw.board.transitions import (
    TransitionNotAllowed,
    is_user_transition_allowed,
)
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
    """High-level operations on the project board.

    user_id can be set at init (dev mode) or passed per-method (auth mode).
    Per-method user_id takes priority over the init default.
    """

    def __init__(self, repo: BoardRepo, user_id: str | None = None) -> None:
        self._repo = repo
        self._default_user_id = user_id
        self._active_user_id: str | None = None

    def set_active_user(self, user_id: str) -> None:
        """Set the user_id for the current request context.

        Called by AgentRunner before each turn so that tool functions
        (which don't receive user_id as a parameter) operate on the
        correct user's board.
        """
        self._active_user_id = user_id

    def _uid(self, user_id: str | None = None) -> str | None:
        return user_id or self._active_user_id or self._default_user_id

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
        user_id: str | None = None,
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
        return self._repo.create(task, user_id=self._uid(user_id))

    def pick_up(self, task_id: str, user_id: str | None = None) -> BoardTask:
        task = self._repo.get(task_id, user_id=self._uid(user_id))
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        updated = task.transition_to(TaskStatus.IN_PROGRESS)
        return self._repo.update(updated, user_id=self._uid(user_id))

    def complete(
        self,
        task_id: str,
        summary: str,
        artifacts: list[str] | None = None,
        user_id: str | None = None,
    ) -> BoardTask:
        task = self._repo.get(task_id, user_id=self._uid(user_id))
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        completed = task.complete(TaskResult(
            summary=summary, artifacts=artifacts or []
        ))
        return self._repo.update(completed, user_id=self._uid(user_id))

    def fail(self, task_id: str, reason: str, user_id: str | None = None) -> BoardTask:
        task = self._repo.get(task_id, user_id=self._uid(user_id))
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        failed = task.transition_to(TaskStatus.FAILED)
        failed = failed.model_copy(
            update={"result": TaskResult(summary=reason)}
        )
        return self._repo.update(failed, user_id=self._uid(user_id))

    def get_pending_tasks(self, assignee: str, user_id: str | None = None) -> list[BoardTask]:
        return self._repo.list_by_assignee(assignee, status=TaskStatus.QUEUED, user_id=self._uid(user_id))

    def get_all_tasks(self, user_id: str | None = None) -> list[BoardTask]:
        return self._repo.list_all(user_id=self._uid(user_id))

    def get_task(
        self, task_id: str, user_id: str | None = None
    ) -> BoardTask | None:
        return self._repo.get(task_id, user_id=self._uid(user_id))

    def move_status(
        self,
        task_id: str,
        target: TaskStatus,
        *,
        user_id: str | None = None,
    ) -> BoardTask:
        """Move a task to ``target`` via a user-initiated transition.

        Raises :class:`TransitionNotAllowed` if the move is not allowed for
        users. Raises ``ValueError`` if the task does not exist.
        """
        uid = self._uid(user_id)
        task = self._repo.get(task_id, user_id=uid)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        if not is_user_transition_allowed(task.status, target):
            raise TransitionNotAllowed(task.status, target)
        updated = task.model_copy(
            update={
                "status": target,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        return self._repo.update(updated, user_id=uid)

    def approve(
        self,
        task_id: str,
        *,
        user_id: str,
        note: str | None = None,
    ) -> BoardTask:
        """Approve a NEEDS_APPROVAL task and move it back to QUEUED."""
        uid = self._uid(user_id)
        task = self._repo.get(task_id, user_id=uid)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        if task.status != TaskStatus.NEEDS_APPROVAL:
            raise ValueError(
                f"Task {task_id} is not awaiting approval "
                f"(status={task.status.value})"
            )
        now = datetime.now(timezone.utc)
        updated = task.model_copy(
            update={
                "status": TaskStatus.QUEUED,
                "approved_at": now,
                "approved_by": user_id,
                "approval_note": note,
                "updated_at": now,
            }
        )
        return self._repo.update(updated, user_id=uid)

    def reject(
        self,
        task_id: str,
        *,
        user_id: str,
        note: str,
    ) -> BoardTask:
        """Reject a NEEDS_APPROVAL task and move it to FAILED."""
        uid = self._uid(user_id)
        task = self._repo.get(task_id, user_id=uid)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        if task.status != TaskStatus.NEEDS_APPROVAL:
            raise ValueError(
                f"Task {task_id} is not awaiting approval "
                f"(status={task.status.value})"
            )
        now = datetime.now(timezone.utc)
        updated = task.model_copy(
            update={
                "status": TaskStatus.FAILED,
                "rejected_at": now,
                "rejection_note": note,
                "updated_at": now,
            }
        )
        return self._repo.update(updated, user_id=uid)
