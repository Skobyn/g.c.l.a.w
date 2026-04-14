"""Tests for cron service business logic."""

import pytest
from unittest.mock import MagicMock

from gclaw.models.cron import (
    AgentTurnPayload,
    Cron,
    CronExprSchedule,
    CronMode,
    CronStatus,
    SystemEventPayload,
)
from gclaw.models.task import BoardTask, TaskStatus
from gclaw.cron.service import CronService


def _make_cron(**overrides):
    base = dict(
        id="cron_1",
        title="My cron",
        assignee="workspace-mgr",
        schedule=CronExprSchedule(expr="0 8 * * *"),
        payload=AgentTurnPayload(message="do it"),
    )
    base.update(overrides)
    return Cron(**base)


@pytest.fixture
def cron_repo():
    repo = MagicMock()
    # The service reaches for ._db / ._user_id for the event queue path.
    repo._db = MagicMock()
    repo._user_id = "user_123"
    return repo


@pytest.fixture
def board_service():
    return MagicMock()


@pytest.fixture
def service(cron_repo, board_service):
    return CronService(cron_repo=cron_repo, board_service=board_service)


# --- create/update/list/pause/resume ---------------------------------------


def test_create_with_legacy_string_schedule(service, cron_repo):
    cron_repo.create.side_effect = lambda c: c
    cron = service.create(
        title="Morning briefing",
        schedule="0 8 * * *",
        assignee="workspace-mgr",
        mode="todo",
        description="Daily morning update",
    )
    assert isinstance(cron.schedule, CronExprSchedule)
    assert cron.schedule.expr == "0 8 * * *"
    assert isinstance(cron.payload, AgentTurnPayload)
    assert cron.payload.message == "Daily morning update"
    assert cron.mode == CronMode.TODO
    assert cron.enabled is True
    cron_repo.create.assert_called_once()


def test_create_with_structured_payload(service, cron_repo):
    cron_repo.create.side_effect = lambda c: c
    cron = service.create(
        title="t",
        schedule=CronExprSchedule(expr="*/5 * * * *"),
        assignee="dev-mgr",
        payload=SystemEventPayload(text="tick"),
        wake_mode="next-heartbeat",
    )
    assert isinstance(cron.payload, SystemEventPayload)
    assert cron.wake_mode == "next-heartbeat"


def test_update_changes_fields(service, cron_repo):
    existing = _make_cron(title="Old")
    cron_repo.get.return_value = existing
    cron_repo.update.side_effect = lambda c: c

    updated = service.update(cron_id="cron_1", title="New", schedule="0 9 * * *")
    assert updated.title == "New"
    assert isinstance(updated.schedule, CronExprSchedule)
    assert updated.schedule.expr == "0 9 * * *"


def test_update_nonexistent_raises(service, cron_repo):
    cron_repo.get.return_value = None
    with pytest.raises(ValueError, match="not found"):
        service.update(cron_id="cron_nope", title="X")


def test_delete(service, cron_repo):
    service.delete("cron_1")
    cron_repo.delete.assert_called_once_with("cron_1")


def test_pause_and_resume_sync_status(service, cron_repo):
    cron = _make_cron(status=CronStatus.ACTIVE, enabled=True)
    cron_repo.get.return_value = cron
    cron_repo.update.side_effect = lambda c: c

    paused = service.pause("cron_1")
    assert paused.status == CronStatus.PAUSED
    assert paused.enabled is False

    cron_repo.get.return_value = paused
    resumed = service.resume("cron_1")
    assert resumed.status == CronStatus.ACTIVE
    assert resumed.enabled is True


# --- execute: agent_turn ---------------------------------------------------


async def test_execute_agent_turn_todo(service, cron_repo, board_service):
    cron = _make_cron(
        mode=CronMode.TODO,
        payload=AgentTurnPayload(message="Check emails"),
        task_priority="medium",
    )
    cron_repo.get.return_value = cron
    cron_repo.update.side_effect = lambda c: c
    board_service.create_task.side_effect = lambda **kw: BoardTask(
        title=kw["title"], assignee=kw["assignee"]
    )

    await service.execute("cron_1")

    kw = board_service.create_task.call_args.kwargs
    assert kw["status"] == TaskStatus.BACKLOG
    assert kw["description"] == "Check emails"
    assert kw["source_type"] == "cron"
    assert kw["source_origin"] == "cron_1"


async def test_execute_agent_turn_auto(service, cron_repo, board_service):
    cron = _make_cron(
        id="cron_2",
        mode=CronMode.AUTO,
        payload=AgentTurnPayload(message="triage"),
        task_priority="high",
    )
    cron_repo.get.return_value = cron
    cron_repo.update.side_effect = lambda c: c
    board_service.create_task.side_effect = lambda **kw: BoardTask(
        title=kw["title"],
        assignee=kw["assignee"],
        status=TaskStatus(kw.get("status", "backlog")),
    )

    await service.execute("cron_2")

    kw = board_service.create_task.call_args.kwargs
    assert kw["status"] == TaskStatus.QUEUED
    assert kw["priority"] == "high"


# --- execute: system_event -------------------------------------------------


async def test_execute_system_event_next_heartbeat_enqueues(
    service, cron_repo, board_service
):
    cron = _make_cron(
        payload=SystemEventPayload(text="stand up"),
        wake_mode="next-heartbeat",
    )
    cron_repo.get.return_value = cron
    cron_repo.update.side_effect = lambda c: c

    # Wire up Firestore collection chain on the mock repo's _db.
    new_doc_ref = MagicMock()
    new_doc_ref.id = "evt_abc"
    col_mock = MagicMock()
    col_mock.document.return_value = new_doc_ref
    cron_repo._db.collection.return_value.document.return_value.collection.return_value = (
        col_mock
    )

    result = await service.execute("cron_1")

    board_service.create_task.assert_not_called()
    new_doc_ref.set.assert_called_once()
    assert result["text"] == "stand up"
    assert result["assignee"] == "workspace-mgr"
    assert result["cron_id"] == "cron_1"


async def test_execute_system_event_wake_now_is_noop(service, cron_repo, board_service):
    cron = _make_cron(
        payload=SystemEventPayload(text="noop"),
        wake_mode="now",
    )
    cron_repo.get.return_value = cron
    cron_repo.update.side_effect = lambda c: c

    result = await service.execute("cron_1")
    assert result is None
    board_service.create_task.assert_not_called()


# --- execute: paused / missing --------------------------------------------


async def test_execute_paused_raises(service, cron_repo):
    cron = _make_cron(status=CronStatus.PAUSED, enabled=False)
    cron_repo.get.return_value = cron
    with pytest.raises(ValueError, match="paused"):
        await service.execute("cron_1")


async def test_execute_missing_raises(service, cron_repo):
    cron_repo.get.return_value = None
    with pytest.raises(ValueError, match="not found"):
        await service.execute("cron_nope")


# --- failure bookkeeping ---------------------------------------------------


async def test_failure_increments_consecutive_errors(
    service, cron_repo, board_service
):
    cron = _make_cron(
        mode=CronMode.AUTO,
        payload=AgentTurnPayload(message="fail me"),
    )
    cron_repo.get.return_value = cron

    recorded: list[Cron] = []

    def _capture_update(c):
        recorded.append(c)
        return c

    cron_repo.update.side_effect = _capture_update
    board_service.create_task.side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await service.execute("cron_1")

    # No failure_alert configured → only the record_failure update lands.
    assert len(recorded) == 1
    assert recorded[0].consecutive_errors == 1
    assert recorded[0].last_error == "boom"


async def test_delete_after_run_removes_cron(service, cron_repo, board_service):
    cron = _make_cron(delete_after_run=True, mode=CronMode.AUTO)
    cron_repo.get.return_value = cron
    cron_repo.update.side_effect = lambda c: c
    board_service.create_task.side_effect = lambda **kw: BoardTask(
        title=kw["title"], assignee=kw["assignee"]
    )
    await service.execute("cron_1")
    cron_repo.delete.assert_called_once_with("cron_1")


async def test_failure_invokes_delivery_failure_alert(
    cron_repo, board_service
):
    """Execute failure path calls delivery.deliver_failure_alert."""
    from unittest.mock import AsyncMock
    from gclaw.models.cron import FailureAlert

    delivery = MagicMock()
    delivery.deliver_success = AsyncMock()
    delivery.deliver_failure_alert = AsyncMock(return_value=True)

    service = CronService(
        cron_repo=cron_repo,
        board_service=board_service,
        delivery_service=delivery,
    )

    cron = _make_cron(
        mode=CronMode.AUTO,
        payload=AgentTurnPayload(message="fail me"),
        failure_alert=FailureAlert(after=1, cooldown_ms=0),
        consecutive_errors=0,
    )
    cron_repo.get.return_value = cron
    cron_repo.update.side_effect = lambda c: c
    board_service.create_task.side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await service.execute("cron_1")

    delivery.deliver_failure_alert.assert_awaited_once()
    # Kwarg: error="boom"
    assert delivery.deliver_failure_alert.call_args.kwargs["error"] == "boom"


async def test_success_invokes_delivery_success(
    cron_repo, board_service
):
    from unittest.mock import AsyncMock

    delivery = MagicMock()
    delivery.deliver_success = AsyncMock()
    delivery.deliver_failure_alert = AsyncMock()

    service = CronService(
        cron_repo=cron_repo,
        board_service=board_service,
        delivery_service=delivery,
    )

    cron = _make_cron(mode=CronMode.AUTO)
    cron_repo.get.return_value = cron
    cron_repo.update.side_effect = lambda c: c
    board_service.create_task.side_effect = lambda **kw: BoardTask(
        title=kw["title"], assignee=kw["assignee"]
    )

    await service.execute("cron_1")

    delivery.deliver_success.assert_awaited_once()
    delivery.deliver_failure_alert.assert_not_called()
