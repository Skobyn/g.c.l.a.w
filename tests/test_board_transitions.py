"""Matrix tests for user-driven board task transitions."""

from __future__ import annotations

import pytest

from gclaw.board.transitions import (
    TransitionNotAllowed,
    USER_ALLOWED,
    is_user_transition_allowed,
)
from gclaw.models.task import TaskStatus


ALL_STATUSES = list(TaskStatus)


@pytest.mark.parametrize("current", ALL_STATUSES)
@pytest.mark.parametrize("target", ALL_STATUSES)
def test_user_transition_matrix(current, target):
    expected = target in USER_ALLOWED.get(current, set())
    assert is_user_transition_allowed(current, target) is expected


def test_backlog_to_queued_allowed():
    assert is_user_transition_allowed(TaskStatus.BACKLOG, TaskStatus.QUEUED)


def test_queued_back_to_backlog_allowed():
    assert is_user_transition_allowed(TaskStatus.QUEUED, TaskStatus.BACKLOG)


def test_in_progress_is_locked_for_users():
    for target in ALL_STATUSES:
        assert not is_user_transition_allowed(TaskStatus.IN_PROGRESS, target)


def test_done_is_terminal_for_users():
    for target in ALL_STATUSES:
        assert not is_user_transition_allowed(TaskStatus.DONE, target)


def test_needs_approval_user_options():
    assert is_user_transition_allowed(
        TaskStatus.NEEDS_APPROVAL, TaskStatus.QUEUED
    )
    assert is_user_transition_allowed(
        TaskStatus.NEEDS_APPROVAL, TaskStatus.FAILED
    )
    assert not is_user_transition_allowed(
        TaskStatus.NEEDS_APPROVAL, TaskStatus.DONE
    )
    assert not is_user_transition_allowed(
        TaskStatus.NEEDS_APPROVAL, TaskStatus.IN_PROGRESS
    )


def test_failed_can_be_requeued_or_sent_back_to_backlog():
    assert is_user_transition_allowed(TaskStatus.FAILED, TaskStatus.QUEUED)
    assert is_user_transition_allowed(TaskStatus.FAILED, TaskStatus.BACKLOG)
    assert not is_user_transition_allowed(
        TaskStatus.FAILED, TaskStatus.IN_PROGRESS
    )


def test_transition_not_allowed_exception_message():
    err = TransitionNotAllowed(TaskStatus.BACKLOG, TaskStatus.DONE)
    msg = str(err)
    assert "backlog" in msg
    assert "done" in msg
    assert err.current == TaskStatus.BACKLOG
    assert err.target == TaskStatus.DONE
    # It's a ValueError subclass so service callers can catch ValueError.
    assert isinstance(err, ValueError)
