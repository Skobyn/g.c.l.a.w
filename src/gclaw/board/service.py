"""Board service — business logic for kanban task management."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

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

    When ``run_registry`` is provided and ``set_active_session`` has been
    called for the current turn, board lifecycle events (task.created,
    task.picked_up, task.completed, task.failed) are pushed into the
    run's event queue so the live chat SSE can render them inline.
    """

    def __init__(
        self,
        repo: BoardRepo,
        user_id: str | None = None,
        run_registry: Any | None = None,
        user_event_registry: Any | None = None,
    ) -> None:
        self._repo = repo
        self._default_user_id = user_id
        self._active_user_id: str | None = None
        self._active_session_id: str | None = None
        self._run_registry = run_registry
        self._user_event_registry = user_event_registry

    def set_active_user(self, user_id: str) -> None:
        """Set the user_id for the current request context.

        Called by AgentRunner before each turn so that tool functions
        (which don't receive user_id as a parameter) operate on the
        correct user's board.
        """
        self._active_user_id = user_id

    def set_active_session(self, session_id: str | None) -> None:
        """Set the session_id (== run_id) for the current turn.

        Called alongside ``set_active_user`` so board-lifecycle events
        (``_emit``) can be fanned to the right run queue.
        """
        self._active_session_id = session_id

    def _uid(self, user_id: str | None = None) -> str | None:
        return user_id or self._active_user_id or self._default_user_id

    def _emit(self, kind: str, task: BoardTask, **extra: Any) -> None:
        """Push a ``task.*`` event to the active channels.

        Dual-writes:
          - RunRegistry (current session) — only if active session is set.
            Drives the inline chat dispatch log.
          - UserEventRegistry (current user) — always if a user can be
            resolved. Drives the background activity strip + cross-session
            notifications.

        Best-effort: exceptions in either path are swallowed so board ops
        never fail because of event plumbing.
        """
        payload = {
            "event": kind,
            "data": {
                "task_id": task.id,
                "title": task.title,
                "priority": task.priority.value,
                "assignee": task.assignee,
                "status": task.status.value,
                "time": datetime.now(timezone.utc).isoformat(),
                **extra,
            },
        }
        if self._run_registry is not None and self._active_session_id:
            try:
                self._run_registry.put_nowait(self._active_session_id, payload)
            except Exception:  # noqa: BLE001
                pass
        if self._user_event_registry is not None:
            uid = self._active_user_id or self._default_user_id
            if uid:
                try:
                    self._user_event_registry.put_nowait(uid, payload)
                except Exception:  # noqa: BLE001
                    pass

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
        created = self._repo.create(task, user_id=self._uid(user_id))
        self._emit("task.created", created)
        return created

    def pick_up(self, task_id: str, user_id: str | None = None) -> BoardTask:
        task = self._repo.get(task_id, user_id=self._uid(user_id))
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        updated = task.transition_to(TaskStatus.IN_PROGRESS)
        saved = self._repo.update(updated, user_id=self._uid(user_id))
        self._emit("task.picked_up", saved)
        return saved

    def complete(
        self,
        task_id: str,
        summary: str,
        artifacts: list[str] | None = None,
        user_id: str | None = None,
    ) -> BoardTask:
        uid = self._uid(user_id)
        task = self._repo.get(task_id, user_id=uid)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        # Real-world agents (notably heartbeat-driven manager runs)
        # sometimes jump from the wake message straight to
        # complete_board_task without a prior pickup. The model layer
        # refuses QUEUED → DONE directly and the task gets stuck
        # forever on that heartbeat agent. Transparently flip through
        # IN_PROGRESS here so the caller sees DONE. task.picked_up
        # still fires via ``pick_up``'s emit so the chat UI renders
        # the correct lifecycle.
        if task.status == TaskStatus.QUEUED:
            task = self.pick_up(task_id, user_id=uid)
        completed = task.complete(TaskResult(
            summary=summary, artifacts=artifacts or []
        ))
        saved = self._repo.update(completed, user_id=uid)
        self._emit("task.completed", saved, summary=summary)
        return saved

    def fail(self, task_id: str, reason: str, user_id: str | None = None) -> BoardTask:
        task = self._repo.get(task_id, user_id=self._uid(user_id))
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        failed = task.transition_to(TaskStatus.FAILED)
        failed = failed.model_copy(
            update={"result": TaskResult(summary=reason)}
        )
        saved = self._repo.update(failed, user_id=self._uid(user_id))
        self._emit("task.failed", saved, reason=reason)
        return saved

    def get_pending_tasks(self, assignee: str, user_id: str | None = None) -> list[BoardTask]:
        return self._repo.list_by_assignee(assignee, status=TaskStatus.QUEUED, user_id=self._uid(user_id))

    def get_all_tasks(self, user_id: str | None = None) -> list[BoardTask]:
        return self._repo.list_all(user_id=self._uid(user_id))

    def get_task(
        self, task_id: str, user_id: str | None = None
    ) -> BoardTask | None:
        return self._repo.get(task_id, user_id=self._uid(user_id))

    def delete_task(
        self, task_id: str, user_id: str | None = None
    ) -> bool:
        """Permanently remove a task. Returns True when a row was
        deleted, False when the task didn't exist.

        Emits ``task.deleted`` so any subscribed UI can update its
        counts without a manual refresh.
        """
        uid = self._uid(user_id)
        task = self._repo.get(task_id, user_id=uid)
        if task is None:
            return False
        self._repo.delete(task_id, user_id=uid)
        # Fire an explicit deleted event so the dashboard + the
        # BoardSummaryCard can decrement their counters.
        self._emit("task.deleted", task)
        return True

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
