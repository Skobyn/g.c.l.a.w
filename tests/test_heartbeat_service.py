"""Tests for heartbeat service — the consciousness loop."""

from datetime import datetime, timedelta, timezone

import pytest
from unittest.mock import MagicMock, AsyncMock

from gclaw.heartbeat.service import HeartbeatService
from gclaw.dispatch.runner import AgentResponse
from gclaw.models.session import Session


@pytest.fixture
def context_gatherer():
    gatherer = MagicMock()
    gatherer.gather.return_value = {
        "current_time": "2026-03-30T12:00:00+00:00",
        "board_summary": {
            "total_tasks": 2,
            "backlog": 0,
            "queued": 1,
            "in_progress": 0,
            "needs_approval": 0,
            "done": 0,
            "failed": 1,
        },
        "failed_tasks": [
            {"id": "t3", "title": "Failed task", "assignee": "dev-mgr"}
        ],
        "pending_approvals": [],
        "stale_tasks": [],
        "cron_summary": {"total_crons": 2},
        "memories": [],
    }
    gatherer.gather_as_message.return_value = (
        "## Heartbeat Wake Cycle\n\n"
        "**Time:** 2026-03-30T12:00:00+00:00\n\n"
        "### Board Summary\n"
        "- Total tasks: 2\n"
        "- Failed: 1\n\n"
        "### Failed Tasks\n"
        "- [t3] Failed task (assignee: dev-mgr)\n"
    )
    return gatherer


@pytest.fixture
def agent_runner():
    runner = AsyncMock()
    runner.run.return_value = AgentResponse(
        text="I see a failed task t3. I'll create a retry task for it.",
        tool_calls=[
            {
                "name": "create_board_task",
                "args": {
                    "title": "Retry: Failed task",
                    "assignee": "dev-mgr",
                },
            }
        ],
        is_final=True,
    )
    return runner


@pytest.fixture
def log_repo():
    return MagicMock()


@pytest.fixture
def service(context_gatherer, agent_runner, log_repo):
    return HeartbeatService(
        context_gatherer=context_gatherer,
        agent_runner=agent_runner,
        log_repo=log_repo,
        user_id="user_123",
        session_id="heartbeat_session",
    )


@pytest.mark.asyncio
async def test_heartbeat_runs_full_cycle(service, context_gatherer, agent_runner, log_repo):
    result = await service.run()

    # Context was gathered
    context_gatherer.gather.assert_called_once()
    context_gatherer.gather_as_message.assert_called_once()

    # Orchestrator was invoked
    agent_runner.run.assert_called_once()
    call_kwargs = agent_runner.run.call_args.kwargs
    assert call_kwargs["user_id"] == "user_123"
    assert call_kwargs["session_id"] == "heartbeat_session"
    assert "Heartbeat" in call_kwargs["message"]

    # Log was saved
    log_repo.save.assert_called_once()

    # Result contains the orchestrator's response
    assert "failed task" in result["orchestrator_response"].lower()
    assert result["actions_taken"] is not None


@pytest.mark.asyncio
async def test_heartbeat_silent_when_board_empty(log_repo):
    gatherer = MagicMock()
    gatherer.gather.return_value = {
        "current_time": "2026-03-30T12:00:00+00:00",
        "board_summary": {
            "total_tasks": 0,
            "backlog": 0,
            "queued": 0,
            "in_progress": 0,
            "needs_approval": 0,
            "done": 0,
            "failed": 0,
        },
        "failed_tasks": [],
        "pending_approvals": [],
        "stale_tasks": [],
        "cron_summary": {"total_crons": 0},
        "memories": [],
    }
    gatherer.gather_as_message.return_value = (
        "## Heartbeat Wake Cycle\n\n"
        "Board is empty. Nothing to do."
    )

    runner = AsyncMock()
    runner.run.return_value = AgentResponse(
        text="All quiet. Going back to sleep.",
        tool_calls=[],
        is_final=True,
    )

    service = HeartbeatService(
        context_gatherer=gatherer,
        agent_runner=runner,
        log_repo=log_repo,
        user_id="user_123",
        session_id="heartbeat_session",
    )

    result = await service.run()

    assert "quiet" in result["orchestrator_response"].lower() or "sleep" in result["orchestrator_response"].lower()
    log_repo.save.assert_called_once()


@pytest.mark.asyncio
async def test_heartbeat_logs_context_summary(service, log_repo):
    await service.run()

    saved_log = log_repo.save.call_args[0][0]
    assert saved_log.context_summary is not None
    assert "2" in saved_log.context_summary or "tasks" in saved_log.context_summary.lower()
    assert saved_log.reasoning is not None


# ---------------------------------------------------------------------------
# Auto-end stale sessions (Item 6)
# ---------------------------------------------------------------------------


def _stale_session(session_id: str, age_seconds: int) -> Session:
    updated = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    return Session(
        id=session_id, user_id="user_123", updated_at=updated
    )


@pytest.mark.asyncio
async def test_heartbeat_auto_ends_stale_sessions(
    context_gatherer, agent_runner, log_repo
):
    session_store = MagicMock()
    session_store.list_active_older_than.return_value = [
        _stale_session("sess_old_1", 7200),
        _stale_session("sess_old_2", 9000),
    ]
    session_store.end_session = AsyncMock(return_value=None)

    service = HeartbeatService(
        context_gatherer=context_gatherer,
        agent_runner=agent_runner,
        log_repo=log_repo,
        user_id="user_123",
        session_id="heartbeat_session",
        session_store=session_store,
        stale_session_threshold_seconds=3600,
    )

    await service.run()

    session_store.list_active_older_than.assert_called_once()
    cutoff_arg = session_store.list_active_older_than.call_args.args[0]
    # Cutoff must be ~3600s before now
    delta = (datetime.now(timezone.utc) - cutoff_arg).total_seconds()
    assert 3500 < delta < 3700

    assert session_store.end_session.await_count == 2
    ended_ids = [c.args[0] for c in session_store.end_session.call_args_list]
    assert set(ended_ids) == {"sess_old_1", "sess_old_2"}


@pytest.mark.asyncio
async def test_heartbeat_does_not_end_own_session(
    context_gatherer, agent_runner, log_repo
):
    session_store = MagicMock()
    # Include the heartbeat's own session in the stale list — it must be skipped.
    session_store.list_active_older_than.return_value = [
        _stale_session("heartbeat_session", 99999),
        _stale_session("sess_other", 7200),
    ]
    session_store.end_session = AsyncMock(return_value=None)

    service = HeartbeatService(
        context_gatherer=context_gatherer,
        agent_runner=agent_runner,
        log_repo=log_repo,
        user_id="user_123",
        session_id="heartbeat_session",
        session_store=session_store,
    )

    await service.run()

    # Only sess_other should have been ended; the heartbeat's own session is protected.
    session_store.end_session.assert_awaited_once_with("sess_other")


@pytest.mark.asyncio
async def test_heartbeat_auto_end_failure_does_not_break_tick(
    context_gatherer, agent_runner, log_repo
):
    session_store = MagicMock()
    session_store.list_active_older_than.side_effect = RuntimeError("firestore down")

    service = HeartbeatService(
        context_gatherer=context_gatherer,
        agent_runner=agent_runner,
        log_repo=log_repo,
        user_id="user_123",
        session_id="heartbeat_session",
        session_store=session_store,
    )

    # Must not raise.
    result = await service.run()
    assert result is not None
    log_repo.save.assert_called_once()


@pytest.mark.asyncio
async def test_heartbeat_no_session_store_skips_auto_end(
    context_gatherer, agent_runner, log_repo
):
    service = HeartbeatService(
        context_gatherer=context_gatherer,
        agent_runner=agent_runner,
        log_repo=log_repo,
        user_id="user_123",
        session_id="heartbeat_session",
        session_store=None,
    )
    # Should run the full cycle without any session_store calls.
    await service.run()
