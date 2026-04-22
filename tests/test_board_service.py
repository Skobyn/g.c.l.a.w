"""Tests for board service business logic."""

import pytest
from unittest.mock import MagicMock

from gclaw.models.task import (
    BoardTask,
    TaskStatus,
    TaskSource,
    TaskSourceType,
    TaskResult,
)
from gclaw.board.service import BoardService
from gclaw.board.transitions import TransitionNotAllowed


@pytest.fixture
def repo():
    return MagicMock()


@pytest.fixture
def service(repo):
    return BoardService(repo=repo)


def test_create_task_from_user(service, repo):
    repo.create.side_effect = lambda t, user_id=None: t
    task = service.create_task(
        title="Do the thing",
        assignee="workspace-mgr",
        source_type="user",
    )
    assert task.title == "Do the thing"
    assert task.source.type == TaskSourceType.USER
    assert task.status == TaskStatus.BACKLOG
    repo.create.assert_called_once()


def test_create_task_from_agent(service, repo):
    repo.create.side_effect = lambda t, user_id=None: t
    task = service.create_task(
        title="Subtask",
        assignee="workspace-mgr",
        source_type="agent",
        source_origin="research-mgr",
        status=TaskStatus.QUEUED,
    )
    assert task.source.type == TaskSourceType.AGENT
    assert task.source.origin == "research-mgr"
    assert task.status == TaskStatus.QUEUED


def test_pick_up_task(service, repo):
    task = BoardTask(
        id="task_1",
        title="Queued task",
        assignee="workspace-mgr",
        status=TaskStatus.QUEUED,
    )
    repo.get.return_value = task
    repo.update.side_effect = lambda t, user_id=None: t

    picked = service.pick_up("task_1")
    assert picked.status == TaskStatus.IN_PROGRESS
    repo.update.assert_called_once()


def test_pick_up_nonexistent_raises(service, repo):
    repo.get.return_value = None
    with pytest.raises(ValueError, match="not found"):
        service.pick_up("nope")


def test_complete_task(service, repo):
    task = BoardTask(
        id="task_1",
        title="In progress task",
        assignee="dev-mgr",
        status=TaskStatus.IN_PROGRESS,
    )
    repo.get.return_value = task
    repo.update.side_effect = lambda t, user_id=None: t

    completed = service.complete(
        "task_1", summary="All done", artifacts=["out.txt"]
    )
    assert completed.status == TaskStatus.DONE
    assert completed.result.summary == "All done"


def test_fail_task(service, repo):
    task = BoardTask(
        id="task_1",
        title="Failing task",
        assignee="dev-mgr",
        status=TaskStatus.IN_PROGRESS,
    )
    repo.get.return_value = task
    repo.update.side_effect = lambda t, user_id=None: t

    failed = service.fail("task_1", reason="API timeout")
    assert failed.status == TaskStatus.FAILED
    assert failed.result.summary == "API timeout"


def test_get_pending_tasks_for_agent(service, repo):
    tasks = [
        BoardTask(id="t1", title="T1", assignee="workspace-mgr", status=TaskStatus.QUEUED),
    ]
    repo.list_by_assignee.return_value = tasks

    result = service.get_pending_tasks("workspace-mgr")
    assert len(result) == 1
    repo.list_by_assignee.assert_called_with(
        "workspace-mgr", status=TaskStatus.QUEUED, user_id=None
    )


# ── Event emission via RunRegistry ──────────────────────────────────


class _FakeRegistry:
    """Minimal RunRegistry shape — capture put_nowait calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def put_nowait(self, run_id: str, event: dict) -> None:
        self.calls.append((run_id, event))


@pytest.fixture
def registry():
    return _FakeRegistry()


@pytest.fixture
def service_with_registry(repo, registry):
    svc = BoardService(repo=repo, run_registry=registry)
    svc.set_active_session("sess_abc")
    return svc


def test_create_task_emits_task_created(service_with_registry, repo, registry):
    repo.create.side_effect = lambda t, user_id=None: t.model_copy(update={"id": "t_001"})
    service_with_registry.create_task(
        title="Do thing", assignee="dev-mgr", source_type="user",
    )
    assert len(registry.calls) == 1
    run_id, event = registry.calls[0]
    assert run_id == "sess_abc"
    assert event["event"] == "task.created"
    assert event["data"]["task_id"] == "t_001"
    assert event["data"]["assignee"] == "dev-mgr"
    assert event["data"]["title"] == "Do thing"
    assert "time" in event["data"]


def test_pick_up_emits_task_picked_up(service_with_registry, repo, registry):
    task = BoardTask(
        id="t_002", title="Queued", assignee="dev-mgr", status=TaskStatus.QUEUED
    )
    repo.get.return_value = task
    repo.update.side_effect = lambda t, user_id=None: t
    service_with_registry.pick_up("t_002")
    assert [c[1]["event"] for c in registry.calls] == ["task.picked_up"]
    assert registry.calls[0][1]["data"]["status"] == TaskStatus.IN_PROGRESS.value


def test_complete_emits_task_completed_with_summary(
    service_with_registry, repo, registry
):
    task = BoardTask(
        id="t_003", title="Running", assignee="dev-mgr", status=TaskStatus.IN_PROGRESS
    )
    repo.get.return_value = task
    repo.update.side_effect = lambda t, user_id=None: t
    service_with_registry.complete("t_003", summary="All good")
    ev = registry.calls[0][1]
    assert ev["event"] == "task.completed"
    assert ev["data"]["summary"] == "All good"


def test_fail_emits_task_failed_with_reason(
    service_with_registry, repo, registry
):
    task = BoardTask(
        id="t_004", title="Trying", assignee="dev-mgr", status=TaskStatus.IN_PROGRESS
    )
    repo.get.return_value = task
    repo.update.side_effect = lambda t, user_id=None: t
    service_with_registry.fail("t_004", reason="timeout")
    ev = registry.calls[0][1]
    assert ev["event"] == "task.failed"
    assert ev["data"]["reason"] == "timeout"


def test_no_emission_when_no_active_session(repo, registry):
    svc = BoardService(repo=repo, run_registry=registry)
    # deliberately do NOT call set_active_session
    repo.create.side_effect = lambda t, user_id=None: t.model_copy(update={"id": "x"})
    svc.create_task(title="X", assignee="dev-mgr")
    assert registry.calls == []


def test_no_emission_when_no_registry(repo):
    svc = BoardService(repo=repo)
    svc.set_active_session("sess_xyz")
    repo.create.side_effect = lambda t, user_id=None: t.model_copy(update={"id": "y"})
    # Should not raise; just no-op on emit.
    svc.create_task(title="Y", assignee="dev-mgr")


# ── Dual-write to UserEventRegistry (PR B) ──────────────────────────


class _FakeUserRegistry:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def put_nowait(self, user_id: str, event: dict) -> None:
        self.calls.append((user_id, event))


def test_create_task_also_emits_to_user_event_registry(repo):
    reg = _FakeRegistry()
    ureg = _FakeUserRegistry()
    svc = BoardService(
        repo=repo, user_id="u_1", run_registry=reg, user_event_registry=ureg
    )
    svc.set_active_session("sess_abc")
    repo.create.side_effect = lambda t, user_id=None: t.model_copy(update={"id": "t_1"})
    svc.create_task(title="X", assignee="dev-mgr")
    assert len(reg.calls) == 1
    assert len(ureg.calls) == 1
    uid, event = ureg.calls[0]
    assert uid == "u_1"
    assert event["event"] == "task.created"


def test_user_event_emits_without_active_session(repo):
    """UserEventRegistry emission works even when no chat session is
    active — that's the whole point of cross-session delivery (e.g.
    heartbeat-driven manager runs in a 'heartbeat' session)."""
    ureg = _FakeUserRegistry()
    svc = BoardService(repo=repo, user_id="u_2", user_event_registry=ureg)
    # Deliberately no set_active_session call.
    repo.create.side_effect = lambda t, user_id=None: t.model_copy(update={"id": "t_2"})
    svc.create_task(title="Heartbeat-picked", assignee="dev-mgr")
    assert len(ureg.calls) == 1
    assert ureg.calls[0][0] == "u_2"


def test_user_event_uses_active_user_over_default(repo):
    ureg = _FakeUserRegistry()
    svc = BoardService(repo=repo, user_id="u_default", user_event_registry=ureg)
    svc.set_active_user("u_active")
    repo.create.side_effect = lambda t, user_id=None: t.model_copy(update={"id": "t_3"})
    svc.create_task(title="X", assignee="dev-mgr")
    assert ureg.calls[0][0] == "u_active"


def test_move_status_allowed(service, repo):
    task = BoardTask(
        id="t1",
        title="T",
        assignee="workspace-mgr",
        status=TaskStatus.BACKLOG,
    )
    repo.get.return_value = task
    repo.update.side_effect = lambda t, user_id=None: t

    moved = service.move_status("t1", TaskStatus.QUEUED, user_id="u1")
    assert moved.status == TaskStatus.QUEUED


def test_move_status_forbidden_raises(service, repo):
    task = BoardTask(
        id="t1",
        title="T",
        assignee="workspace-mgr",
        status=TaskStatus.BACKLOG,
    )
    repo.get.return_value = task

    with pytest.raises(TransitionNotAllowed):
        service.move_status("t1", TaskStatus.DONE, user_id="u1")
    repo.update.assert_not_called()


def test_move_status_missing_task_raises(service, repo):
    repo.get.return_value = None
    with pytest.raises(ValueError, match="not found"):
        service.move_status("nope", TaskStatus.QUEUED, user_id="u1")


def test_approve_happy_path(service, repo):
    task = BoardTask(
        id="t1",
        title="T",
        assignee="workspace-mgr",
        status=TaskStatus.NEEDS_APPROVAL,
    )
    repo.get.return_value = task
    repo.update.side_effect = lambda t, user_id=None: t

    approved = service.approve("t1", user_id="u1", note="go ahead")
    assert approved.status == TaskStatus.QUEUED
    assert approved.approved_by == "u1"
    assert approved.approved_at is not None
    assert approved.approval_note == "go ahead"


def test_approve_wrong_status_raises(service, repo):
    task = BoardTask(
        id="t1",
        title="T",
        assignee="workspace-mgr",
        status=TaskStatus.QUEUED,
    )
    repo.get.return_value = task

    with pytest.raises(ValueError, match="not awaiting approval"):
        service.approve("t1", user_id="u1")


def test_reject_happy_path(service, repo):
    task = BoardTask(
        id="t1",
        title="T",
        assignee="workspace-mgr",
        status=TaskStatus.NEEDS_APPROVAL,
    )
    repo.get.return_value = task
    repo.update.side_effect = lambda t, user_id=None: t

    rejected = service.reject("t1", user_id="u1", note="bad idea")
    assert rejected.status == TaskStatus.FAILED
    assert rejected.rejection_note == "bad idea"
    assert rejected.rejected_at is not None


def test_reject_wrong_status_raises(service, repo):
    task = BoardTask(
        id="t1",
        title="T",
        assignee="workspace-mgr",
        status=TaskStatus.DONE,
    )
    repo.get.return_value = task

    with pytest.raises(ValueError, match="not awaiting approval"):
        service.reject("t1", user_id="u1", note="no")
