"""Tests for heartbeat context gatherer."""

import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone

from gclaw.models.task import BoardTask, TaskStatus, TaskPriority
from gclaw.models.cron import Cron, CronMode
from gclaw.heartbeat.context import HeartbeatContextGatherer


@pytest.fixture
def board_service():
    return MagicMock()


@pytest.fixture
def cron_service():
    return MagicMock()


@pytest.fixture
def gatherer(board_service, cron_service):
    return HeartbeatContextGatherer(
        board_service=board_service,
        cron_service=cron_service,
    )


def test_gather_empty_board(gatherer, board_service, cron_service):
    board_service.get_all_tasks.return_value = []
    cron_service.list_all.return_value = []

    ctx = gatherer.gather()

    assert "current_time" in ctx
    assert ctx["board_summary"]["total_tasks"] == 0
    assert ctx["board_summary"]["queued"] == 0
    assert ctx["board_summary"]["in_progress"] == 0
    assert ctx["board_summary"]["failed"] == 0
    assert ctx["board_summary"]["needs_approval"] == 0
    assert ctx["stale_tasks"] == []
    assert ctx["failed_tasks"] == []
    assert ctx["pending_approvals"] == []
    assert ctx["cron_summary"]["total_crons"] == 0


def test_gather_with_tasks(gatherer, board_service, cron_service):
    tasks = [
        BoardTask(
            id="t1", title="Queued task", assignee="dev-mgr",
            status=TaskStatus.QUEUED, priority=TaskPriority.HIGH,
        ),
        BoardTask(
            id="t2", title="In progress task", assignee="workspace-mgr",
            status=TaskStatus.IN_PROGRESS,
        ),
        BoardTask(
            id="t3", title="Failed task", assignee="dev-mgr",
            status=TaskStatus.FAILED,
        ),
        BoardTask(
            id="t4", title="Needs approval", assignee="comms-mgr",
            status=TaskStatus.NEEDS_APPROVAL,
        ),
        BoardTask(
            id="t5", title="Done task", assignee="dev-mgr",
            status=TaskStatus.DONE,
        ),
    ]
    board_service.get_all_tasks.return_value = tasks
    cron_service.list_all.return_value = []

    ctx = gatherer.gather()

    assert ctx["board_summary"]["total_tasks"] == 5
    assert ctx["board_summary"]["queued"] == 1
    assert ctx["board_summary"]["in_progress"] == 1
    assert ctx["board_summary"]["failed"] == 1
    assert ctx["board_summary"]["needs_approval"] == 1
    assert ctx["board_summary"]["done"] == 1
    assert len(ctx["failed_tasks"]) == 1
    assert ctx["failed_tasks"][0]["id"] == "t3"
    assert len(ctx["pending_approvals"]) == 1
    assert ctx["pending_approvals"][0]["id"] == "t4"


def test_gather_with_crons(gatherer, board_service, cron_service):
    board_service.get_all_tasks.return_value = []
    from gclaw.models.cron import AgentTurnPayload, CronExprSchedule
    cron_service.list_all.return_value = [
        Cron(
            title="C1",
            schedule=CronExprSchedule(expr="0 8 * * *"),
            payload=AgentTurnPayload(message="do"),
            assignee="dev-mgr",
        ),
        Cron(
            title="C2",
            schedule=CronExprSchedule(expr="0 9 * * *"),
            payload=AgentTurnPayload(message="do"),
            assignee="workspace-mgr",
            mode=CronMode.AUTO,
        ),
    ]

    ctx = gatherer.gather()

    assert ctx["cron_summary"]["total_crons"] == 2


def test_gather_formats_as_message(gatherer, board_service, cron_service):
    board_service.get_all_tasks.return_value = [
        BoardTask(
            id="t1", title="Failed task", assignee="dev-mgr",
            status=TaskStatus.FAILED,
        ),
    ]
    cron_service.list_all.return_value = []

    message = gatherer.gather_as_message()

    assert isinstance(message, str)
    assert "Heartbeat" in message
    assert "failed" in message.lower()
    assert "t1" in message


# ── Per-agent my_queue (PR B) ───────────────────────────────────────


def test_gather_includes_my_queue_for_named_agent(board_service, cron_service):
    """When agent_name is set, gather returns a priority-sorted queue
    of QUEUED tasks assigned to that specific agent."""
    tasks = [
        BoardTask(id="t_hi", title="Urgent", assignee="dev-mgr",
                  status=TaskStatus.QUEUED, priority=TaskPriority.HIGH),
        BoardTask(id="t_lo", title="Later", assignee="dev-mgr",
                  status=TaskStatus.QUEUED, priority=TaskPriority.LOW),
        BoardTask(id="t_med", title="Soon", assignee="dev-mgr",
                  status=TaskStatus.QUEUED, priority=TaskPriority.MEDIUM),
        BoardTask(id="t_other", title="Not mine", assignee="comms-mgr",
                  status=TaskStatus.QUEUED, priority=TaskPriority.HIGH),
        BoardTask(id="t_done", title="Done already", assignee="dev-mgr",
                  status=TaskStatus.DONE, priority=TaskPriority.HIGH),
    ]
    board_service.get_all_tasks.return_value = tasks
    cron_service.list_all.return_value = []

    g = HeartbeatContextGatherer(
        board_service=board_service,
        cron_service=cron_service,
        agent_name="dev-mgr",
    )
    ctx = g.gather()

    # Only QUEUED + assigned to dev-mgr, sorted HIGH → MED → LOW
    ids = [t["id"] for t in ctx["my_queue"]]
    assert ids == ["t_hi", "t_med", "t_lo"]
    assert ctx["agent_name"] == "dev-mgr"


def test_gather_empty_my_queue_for_anonymous_gatherer(
    gatherer, board_service, cron_service
):
    """gatherer with no agent_name gets an empty my_queue — legacy
    orchestrator path unaffected."""
    board_service.get_all_tasks.return_value = [
        BoardTask(id="t1", title="x", assignee="dev-mgr",
                  status=TaskStatus.QUEUED, priority=TaskPriority.HIGH),
    ]
    cron_service.list_all.return_value = []
    ctx = gatherer.gather()
    assert ctx["my_queue"] == []
    assert ctx["agent_name"] is None


def test_message_includes_my_queue_with_pickup_instruction(
    board_service, cron_service,
):
    board_service.get_all_tasks.return_value = [
        BoardTask(id="t_1", title="Draft that email", assignee="comms-mgr",
                  status=TaskStatus.QUEUED, priority=TaskPriority.MEDIUM,
                  description="Reply re: Q2 planning"),
    ]
    cron_service.list_all.return_value = []
    g = HeartbeatContextGatherer(
        board_service=board_service,
        cron_service=cron_service,
        agent_name="comms-mgr",
    )
    msg = g.gather_as_message()
    assert "Your Pending Queue" in msg
    assert "t_1" in msg
    assert "Draft that email" in msg
    assert "get_board_task" in msg
    assert "complete_board_task" in msg
