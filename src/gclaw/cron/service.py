"""Cron service — business logic for scheduled task management."""

from __future__ import annotations

from gclaw.board.service import BoardService
from gclaw.firestore.cron_repo import CronRepo
from gclaw.models.cron import Cron, CronMode, CronStatus
from gclaw.models.task import TaskStatus


class CronService:
    """High-level operations on cron definitions."""

    def __init__(
        self,
        cron_repo: CronRepo,
        board_service: BoardService,
    ) -> None:
        self._repo = cron_repo
        self._board = board_service

    def create(
        self,
        title: str,
        schedule: str,
        assignee: str,
        mode: str = "todo",
        description: str = "",
        task_priority: str = "medium",
    ) -> Cron:
        cron = Cron(
            title=title,
            description=description,
            schedule=schedule,
            mode=CronMode(mode),
            assignee=assignee,
            task_priority=task_priority,
        )
        return self._repo.create(cron)

    def update(
        self,
        cron_id: str,
        title: str | None = None,
        schedule: str | None = None,
        mode: str | None = None,
        description: str | None = None,
        assignee: str | None = None,
        task_priority: str | None = None,
    ) -> Cron:
        cron = self._repo.get(cron_id)
        if cron is None:
            raise ValueError(f"Cron {cron_id} not found")

        updates: dict = {}
        if title is not None:
            updates["title"] = title
        if schedule is not None:
            updates["schedule"] = schedule
        if mode is not None:
            updates["mode"] = CronMode(mode)
        if description is not None:
            updates["description"] = description
        if assignee is not None:
            updates["assignee"] = assignee
        if task_priority is not None:
            updates["task_priority"] = task_priority

        updated = cron.model_copy(update=updates)
        return self._repo.update(updated)

    def delete(self, cron_id: str) -> None:
        self._repo.delete(cron_id)

    def list_all(self) -> list[Cron]:
        return self._repo.list_all()

    def pause(self, cron_id: str) -> Cron:
        cron = self._repo.get(cron_id)
        if cron is None:
            raise ValueError(f"Cron {cron_id} not found")
        paused = cron.model_copy(update={"status": CronStatus.PAUSED})
        return self._repo.update(paused)

    def resume(self, cron_id: str) -> Cron:
        cron = self._repo.get(cron_id)
        if cron is None:
            raise ValueError(f"Cron {cron_id} not found")
        resumed = cron.model_copy(update={"status": CronStatus.ACTIVE})
        return self._repo.update(resumed)

    def execute(self, cron_id: str) -> None:
        """Execute a cron: create a task on the board based on mode.

        - mode="todo": create task in BACKLOG
        - mode="auto": create task in QUEUED (ready for immediate pickup)

        Returns the created BoardTask.
        """
        cron = self._repo.get(cron_id)
        if cron is None:
            raise ValueError(f"Cron {cron_id} not found")
        if cron.status == CronStatus.PAUSED:
            raise ValueError(
                f"Cron {cron_id} is paused — resume it before executing"
            )

        # Determine task status based on cron mode
        if cron.mode == CronMode.AUTO:
            task_status = TaskStatus.QUEUED
        else:
            task_status = TaskStatus.BACKLOG

        # Create the task on the board
        task = self._board.create_task(
            title=cron.title,
            assignee=cron.assignee,
            description=cron.description,
            priority=cron.task_priority,
            source_type="cron",
            source_origin=cron.id,
            status=task_status,
        )

        # Record the run
        updated_cron = cron.record_run()
        self._repo.update(updated_cron)

        return task
