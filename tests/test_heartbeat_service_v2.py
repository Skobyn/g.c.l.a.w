"""v2 heartbeat service behaviour — gating, HEARTBEAT_OK protocol, cron drain."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from gclaw.dispatch.runner import AgentResponse
from gclaw.heartbeat.config import ActiveHours, HeartbeatConfig
from gclaw.heartbeat.events import HeartbeatStatus, get_event_bus
from gclaw.heartbeat.reason import WakeReason
from gclaw.heartbeat.service import HeartbeatService


def _busy_context() -> dict:
    return {
        "current_time": "2026-04-14T12:00:00+00:00",
        "board_summary": {
            "total_tasks": 1,
            "backlog": 0,
            "queued": 0,
            "in_progress": 0,
            "needs_approval": 0,
            "done": 0,
            "failed": 1,
        },
        "failed_tasks": [],
        "pending_approvals": [],
        "stale_tasks": [],
        "cron_summary": {"total_crons": 0},
        "memories": [],
    }


def _empty_context() -> dict:
    return {
        "current_time": "2026-04-14T12:00:00+00:00",
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


def _gatherer(ctx: dict, msg: str = "CTX"):
    g = MagicMock()
    g.gather.return_value = ctx
    g.gather_as_message.return_value = msg
    return g


def _runner(text: str, tool_calls=None):
    r = AsyncMock()
    r.run.return_value = AgentResponse(
        text=text,
        tool_calls=tool_calls or [],
        is_final=True,
    )
    return r


def _service(gatherer, runner, **kw):
    return HeartbeatService(
        context_gatherer=gatherer,
        agent_runner=runner,
        log_repo=MagicMock(),
        user_id="user_123",
        session_id="heartbeat",
        agent_name=kw.pop("agent_name", "orchestrator"),
        **kw,
    )


def _recent_for(agent_id: str):
    return get_event_bus().recent(limit=50, agent_id=agent_id)


# ---------------------------------------------------------------- gating


@pytest.mark.asyncio
async def test_skipped_outside_active_hours():
    agent_id = "hb_outside_1"
    # Window that does not include any real wall-clock time either side
    # — use a 1-minute dead-zone far from "now" is unreliable; instead
    # build a window that's the *complement* of the current hour.
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    dead_start = (now + timedelta(hours=2)).strftime("%H:%M")
    dead_end = (now + timedelta(hours=4)).strftime("%H:%M")
    cfg = HeartbeatConfig(
        enabled=True,
        active_hours=ActiveHours(start=dead_start, end=dead_end),
    )
    gatherer = _gatherer(_busy_context())
    runner = _runner("should not run")
    svc = _service(gatherer, runner, heartbeat_config=cfg, agent_name=agent_id)

    result = await svc.run()

    assert result["status"] == HeartbeatStatus.SKIPPED
    runner.run.assert_not_called()
    events = _recent_for(agent_id)
    assert events[0].status == HeartbeatStatus.SKIPPED


@pytest.mark.asyncio
async def test_empty_board_interval_skips_with_ok_empty():
    agent_id = "hb_empty_1"
    gatherer = _gatherer(_empty_context())
    runner = _runner("should not run")
    svc = _service(
        gatherer,
        runner,
        agent_name=agent_id,
        heartbeat_config=HeartbeatConfig(enabled=True),
    )

    result = await svc.run(WakeReason.INTERVAL)

    assert result["status"] == HeartbeatStatus.OK_EMPTY
    runner.run.assert_not_called()
    events = _recent_for(agent_id)
    assert events[0].status == HeartbeatStatus.OK_EMPTY


@pytest.mark.asyncio
async def test_manual_reason_bypasses_empty_gate():
    agent_id = "hb_manual_1"
    gatherer = _gatherer(_empty_context())
    runner = _runner("forced reply")
    svc = _service(
        gatherer,
        runner,
        agent_name=agent_id,
        heartbeat_config=HeartbeatConfig(enabled=True),
    )

    result = await svc.run(WakeReason.MANUAL)

    assert result["status"] == HeartbeatStatus.SENT
    runner.run.assert_awaited_once()


# ------------------------------------------------- HEARTBEAT_OK parsing


@pytest.mark.asyncio
async def test_bare_ok_token_maps_to_ok_token_and_skips_log():
    agent_id = "hb_ok_1"
    log_repo = MagicMock()
    gatherer = _gatherer(_busy_context())
    runner = _runner("HEARTBEAT_OK")
    svc = HeartbeatService(
        context_gatherer=gatherer,
        agent_runner=runner,
        log_repo=log_repo,
        user_id="u",
        agent_name=agent_id,
    )

    result = await svc.run()

    assert result["status"] == HeartbeatStatus.OK_TOKEN
    log_repo.save.assert_not_called()
    events = _recent_for(agent_id)
    assert events[0].status == HeartbeatStatus.OK_TOKEN


@pytest.mark.asyncio
async def test_ok_token_with_short_ack_is_ok_token():
    agent_id = "hb_ok_2"
    log_repo = MagicMock()
    gatherer = _gatherer(_busy_context())
    runner = _runner("HEARTBEAT_OK all quiet")
    svc = HeartbeatService(
        context_gatherer=gatherer,
        agent_runner=runner,
        log_repo=log_repo,
        user_id="u",
        agent_name=agent_id,
        heartbeat_config=HeartbeatConfig(ack_max_chars=30),
    )

    result = await svc.run()

    assert result["status"] == HeartbeatStatus.OK_TOKEN
    log_repo.save.assert_not_called()


@pytest.mark.asyncio
async def test_full_reply_is_sent_and_logs():
    agent_id = "hb_sent_1"
    log_repo = MagicMock()
    gatherer = _gatherer(_busy_context())
    runner = _runner("I notice a failure, creating a retry task.")
    svc = HeartbeatService(
        context_gatherer=gatherer,
        agent_runner=runner,
        log_repo=log_repo,
        user_id="u",
        agent_name=agent_id,
    )

    result = await svc.run()

    assert result["status"] == HeartbeatStatus.SENT
    log_repo.save.assert_called_once()
    events = _recent_for(agent_id)
    assert events[0].status == HeartbeatStatus.SENT


@pytest.mark.asyncio
async def test_ok_token_with_long_ack_counts_as_sent():
    agent_id = "hb_long_1"
    long_ack = "x" * 100
    gatherer = _gatherer(_busy_context())
    runner = _runner(f"HEARTBEAT_OK {long_ack}")
    svc = HeartbeatService(
        context_gatherer=gatherer,
        agent_runner=runner,
        log_repo=MagicMock(),
        user_id="u",
        agent_name=agent_id,
        heartbeat_config=HeartbeatConfig(ack_max_chars=30),
    )

    result = await svc.run()

    assert result["status"] == HeartbeatStatus.SENT


# ------------------------------------------------- cron event drain


@pytest.mark.asyncio
async def test_cron_events_drained_and_prepended_before_agent_call():
    agent_id = "hb_drain_1"
    queue = MagicMock()
    queue.list_pending.return_value = [
        {"id": "e1", "text": "reminder: standup in 5 min"},
        {"id": "e2", "text": "deploy completed"},
    ]
    queue.mark_drained = MagicMock()

    gatherer = _gatherer(_busy_context(), msg="BASE_CTX")
    runner = _runner("Acknowledged.")
    svc = HeartbeatService(
        context_gatherer=gatherer,
        agent_runner=runner,
        log_repo=MagicMock(),
        user_id="u",
        agent_name=agent_id,
        cron_event_queue_repo=queue,
    )

    result = await svc.run(WakeReason.INTERVAL)

    # Drain was called with the agent name, before the agent.run.
    queue.list_pending.assert_called_once_with(agent_id)

    # Message prepended the events before the base context.
    sent_msg = runner.run.call_args.kwargs["message"]
    assert "reminder: standup in 5 min" in sent_msg
    assert "deploy completed" in sent_msg
    assert sent_msg.index("reminder") < sent_msg.index("BASE_CTX")

    # Drained after successful run.
    queue.mark_drained.assert_called_once()
    assert set(queue.mark_drained.call_args[0][0]) == {"e1", "e2"}

    # Reason upgraded from INTERVAL to CRON.
    events = _recent_for(agent_id)
    assert events[0].reason == WakeReason.CRON
    assert result["status"] == HeartbeatStatus.SENT


@pytest.mark.asyncio
async def test_empty_gate_skipped_when_cron_events_present():
    agent_id = "hb_drain_empty_1"
    queue = MagicMock()
    queue.list_pending.return_value = [
        {"id": "e1", "text": "ping"},
    ]
    queue.mark_drained = MagicMock()

    # Empty board — but the cron events should force a run anyway.
    gatherer = _gatherer(_empty_context())
    runner = _runner("HEARTBEAT_OK")
    svc = HeartbeatService(
        context_gatherer=gatherer,
        agent_runner=runner,
        log_repo=MagicMock(),
        user_id="u",
        agent_name=agent_id,
        cron_event_queue_repo=queue,
    )

    result = await svc.run(WakeReason.INTERVAL)

    runner.run.assert_awaited_once()
    assert result["status"] == HeartbeatStatus.OK_TOKEN
    queue.mark_drained.assert_called_once()
