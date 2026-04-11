"""Tests for memory consolidation triggered via heartbeat."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from gclaw.heartbeat.service import HeartbeatService
from gclaw.dispatch.runner import AgentResponse


@pytest.mark.asyncio
async def test_heartbeat_runs_consolidation_when_idle():
    """When board is idle (in_progress==0), consolidation should run."""
    gatherer = MagicMock()
    gatherer.gather.return_value = {
        "board_summary": {
            "total_tasks": 0,
            "queued": 0,
            "in_progress": 0,
            "failed": 0,
            "needs_approval": 0,
        },
    }
    gatherer.gather_as_message.return_value = "No pending tasks."

    runner = AsyncMock()
    runner.run.return_value = AgentResponse(
        text="All clear.",
        tool_calls=[],
        is_final=True,
    )

    consolidator = AsyncMock()
    consolidator.run.return_value = MagicMock(
        memories_scanned=50,
        memories_pruned=5,
        memories_merged=2,
    )

    log_repo = MagicMock()

    service = HeartbeatService(
        context_gatherer=gatherer,
        agent_runner=runner,
        log_repo=log_repo,
        user_id="user1",
        consolidator=consolidator,
    )

    result = await service.run()
    consolidator.run.assert_called_once_with(user_id="user1")
    assert "context" in result


@pytest.mark.asyncio
async def test_heartbeat_skips_consolidation_when_busy():
    """When board is busy (in_progress > 0), consolidation should not run."""
    gatherer = MagicMock()
    gatherer.gather.return_value = {
        "board_summary": {
            "total_tasks": 5,
            "queued": 2,
            "in_progress": 3,
            "failed": 0,
            "needs_approval": 0,
        },
    }
    gatherer.gather_as_message.return_value = "Tasks in progress."

    runner = AsyncMock()
    runner.run.return_value = AgentResponse(
        text="Board is active.",
        tool_calls=[],
        is_final=True,
    )

    consolidator = AsyncMock()
    log_repo = MagicMock()

    service = HeartbeatService(
        context_gatherer=gatherer,
        agent_runner=runner,
        log_repo=log_repo,
        user_id="user1",
        consolidator=consolidator,
    )

    result = await service.run()
    consolidator.run.assert_not_called()
    assert "context" in result


@pytest.mark.asyncio
async def test_heartbeat_works_without_consolidator():
    """Consolidator is optional — heartbeat should work fine without it."""
    gatherer = MagicMock()
    gatherer.gather.return_value = {
        "board_summary": {
            "total_tasks": 0,
            "queued": 0,
            "in_progress": 0,
            "failed": 0,
            "needs_approval": 0,
        },
    }
    gatherer.gather_as_message.return_value = "No pending tasks."

    runner = AsyncMock()
    runner.run.return_value = AgentResponse(
        text="All clear.",
        tool_calls=[],
        is_final=True,
    )

    log_repo = MagicMock()

    service = HeartbeatService(
        context_gatherer=gatherer,
        agent_runner=runner,
        log_repo=log_repo,
        user_id="user1",
        consolidator=None,
    )

    result = await service.run()
    # Should complete without error even with no consolidator
    assert "context" in result
    log_repo.save.assert_called_once()


@pytest.mark.asyncio
async def test_heartbeat_handles_consolidation_failure_gracefully():
    """If consolidation fails, heartbeat should continue and log warning."""
    gatherer = MagicMock()
    gatherer.gather.return_value = {
        "board_summary": {
            "total_tasks": 0,
            "queued": 0,
            "in_progress": 0,
            "failed": 0,
            "needs_approval": 0,
        },
    }
    gatherer.gather_as_message.return_value = "No pending tasks."

    runner = AsyncMock()
    runner.run.return_value = AgentResponse(
        text="All clear.",
        tool_calls=[],
        is_final=True,
    )

    consolidator = AsyncMock()
    consolidator.run.side_effect = Exception("Consolidation failed")

    log_repo = MagicMock()

    service = HeartbeatService(
        context_gatherer=gatherer,
        agent_runner=runner,
        log_repo=log_repo,
        user_id="user1",
        consolidator=consolidator,
    )

    result = await service.run()
    # Should complete without raising, despite consolidation error
    assert "context" in result
    log_repo.save.assert_called_once()
