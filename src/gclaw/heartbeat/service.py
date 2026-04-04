"""Heartbeat service — the orchestrator's consciousness loop.

The heartbeat is NOT a health monitor. It is the mechanism that makes
the orchestrator proactive. On each cycle:

1. Gather context (board state, crons, time, memories)
2. Send context to the orchestrator agent as a message
3. Let the orchestrator reason and take action (create tasks, notify, etc.)
4. Log the heartbeat result
5. Run memory consolidation if board is idle
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from gclaw.dispatch.runner import AgentRunner
from gclaw.heartbeat.context import HeartbeatContextGatherer
from gclaw.heartbeat.log import HeartbeatLog, HeartbeatLogRepo

if TYPE_CHECKING:
    from gclaw.memory.consolidation import MemoryConsolidator

logger = logging.getLogger(__name__)


class HeartbeatService:
    """Runs a single heartbeat cycle."""

    def __init__(
        self,
        context_gatherer: HeartbeatContextGatherer,
        agent_runner: AgentRunner,
        log_repo: HeartbeatLogRepo,
        user_id: str,
        session_id: str = "heartbeat",
        consolidator: MemoryConsolidator | None = None,
    ) -> None:
        self._gatherer = context_gatherer
        self._runner = agent_runner
        self._log_repo = log_repo
        self._user_id = user_id
        self._session_id = session_id
        self._consolidator = consolidator

    async def run(self) -> dict:
        """Execute one heartbeat cycle.

        Returns a dict with:
        - orchestrator_response: the agent's text response
        - actions_taken: list of tool calls the agent made
        - context: the raw context dict
        """
        # 1. Gather context
        context = self._gatherer.gather()
        message = self._gatherer.gather_as_message()

        # 2. Send to orchestrator for reasoning
        response = await self._runner.run(
            user_id=self._user_id,
            session_id=self._session_id,
            message=message,
        )

        # 3. Extract actions
        actions_taken = [
            f"{tc['name']}({tc['args']})" for tc in response.tool_calls
        ]
        tasks_created = [
            tc["args"].get("title", "unknown")
            for tc in response.tool_calls
            if tc["name"] == "create_board_task"
        ]

        # 4. Build context summary for the log
        summary = self._build_context_summary(context)

        # 5. Log the heartbeat
        log = HeartbeatLog(
            context_summary=summary,
            reasoning=response.text,
            actions_taken=actions_taken,
            tasks_created=tasks_created,
        )
        self._log_repo.save(log)

        # 6. Run memory consolidation if available and board is idle
        if self._consolidator is not None and context["board_summary"]["in_progress"] == 0:
            try:
                consolidation = await self._consolidator.run(user_id=self._user_id)
                logger.info(
                    "Memory consolidation: scanned=%d pruned=%d merged=%d",
                    consolidation.memories_scanned,
                    consolidation.memories_pruned,
                    consolidation.memories_merged,
                )
            except Exception:
                logger.warning("Memory consolidation failed", exc_info=True)

        return {
            "orchestrator_response": response.text,
            "actions_taken": actions_taken,
            "tasks_created": tasks_created,
            "context": context,
        }

    def _build_context_summary(self, context: dict) -> str:
        """Build a concise summary string from the context dict."""
        bs = context["board_summary"]
        parts = [
            f"{bs['total_tasks']} tasks on board",
            f"({bs['queued']} queued, {bs['in_progress']} in progress, "
            f"{bs['failed']} failed, {bs['needs_approval']} needs approval)",
        ]
        return " ".join(parts)
