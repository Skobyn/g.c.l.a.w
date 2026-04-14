"""Board task status transition rules.

Two sets of rules:

* ``USER_ALLOWED`` — transitions a user may request via the API (e.g. by
  drag-and-drop on the kanban board). Validated server-side as the last
  line of defense against forbidden moves.
* ``AGENT_ALLOWED`` — transitions agents perform through service methods
  (pick_up, complete, fail, request approval). Documented here for clarity;
  enforcement lives in the service layer / model.
"""

from __future__ import annotations

from gclaw.models.task import TaskStatus


# What a USER (via API) is allowed to move.
# Agent-driven transitions (in_progress -> done/failed/needs_approval) go via
# service methods, not this validator.
USER_ALLOWED: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.BACKLOG: {TaskStatus.QUEUED},
    TaskStatus.QUEUED: {TaskStatus.BACKLOG},
    TaskStatus.NEEDS_APPROVAL: {TaskStatus.QUEUED, TaskStatus.FAILED},
    TaskStatus.FAILED: {TaskStatus.QUEUED, TaskStatus.BACKLOG},
    TaskStatus.IN_PROGRESS: set(),  # user can't drag
    TaskStatus.DONE: set(),  # terminal
}


# What agents move through service methods. Informational — enforced by
# the BoardService methods (pick_up, complete, fail, request_approval).
AGENT_ALLOWED: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.QUEUED: {TaskStatus.IN_PROGRESS},
    TaskStatus.IN_PROGRESS: {
        TaskStatus.DONE,
        TaskStatus.FAILED,
        TaskStatus.NEEDS_APPROVAL,
    },
    # backlog/needs_approval/failed/done unchanged by agents directly
}


class TransitionNotAllowed(ValueError):
    """Raised when a requested user-driven transition is forbidden."""

    def __init__(self, current: TaskStatus, target: TaskStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(
            f"Cannot move {current.value} \u2192 {target.value}"
        )


def is_user_transition_allowed(
    current: TaskStatus, target: TaskStatus
) -> bool:
    """Return True iff a user may move a task from ``current`` to ``target``."""
    return target in USER_ALLOWED.get(current, set())
