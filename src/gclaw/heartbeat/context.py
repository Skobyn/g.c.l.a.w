"""Context gatherer for the heartbeat consciousness loop.

Scans the board, crons, memories, and system state to build a context snapshot
that the orchestrator uses to decide what actions to take.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from gclaw.board.service import BoardService
from gclaw.cron.service import CronService
from gclaw.models.task import TaskStatus

if TYPE_CHECKING:
    from gclaw.memory.service import MemoryService

logger = logging.getLogger(__name__)


class HeartbeatContextGatherer:
    """Gathers world state for the orchestrator's heartbeat reasoning."""

    def __init__(
        self,
        board_service: BoardService,
        cron_service: CronService,
        memory_service: MemoryService | None = None,
        user_id: str | None = None,
    ) -> None:
        self._board = board_service
        self._crons = cron_service
        self._memory = memory_service
        self._user_id = user_id

    def gather(self) -> dict:
        """Gather full context snapshot for heartbeat reasoning (sync, no memories).

        Returns a dict with:
        - current_time: ISO timestamp
        - board_summary: task counts by status
        - failed_tasks: list of failed task summaries
        - pending_approvals: tasks needing user approval
        - stale_tasks: tasks stuck in progress (placeholder for time-based check)
        - cron_summary: overview of cron definitions
        - memories: empty list (use gather_async for memory-enriched context)
        """
        return self._gather_board_and_crons([])

    async def gather_async(self) -> dict:
        """Gather full context snapshot including memories from Memory Bank.

        Returns the same dict as gather() but with memories populated
        from Vertex AI Memory Bank if the memory service is available.
        """
        memories = []
        if self._memory is not None and self._user_id is not None:
            try:
                memories = await self._memory.recall(
                    user_id=self._user_id,
                    query="pending tasks, reminders, upcoming events, commitments",
                )
            except Exception:
                logger.warning(
                    "Memory recall failed during heartbeat gather, "
                    "proceeding without memories",
                    exc_info=True,
                )

        return self._gather_board_and_crons(memories)

    def _gather_board_and_crons(self, memories: list) -> dict:
        """Internal helper — gather board + cron state with provided memories."""
        now = datetime.now(timezone.utc)
        tasks = self._board.get_all_tasks()

        # Count tasks by status
        status_counts: dict[str, int] = {}
        for status in TaskStatus:
            status_counts[status.value] = 0
        for task in tasks:
            status_counts[task.status.value] += 1

        # Collect notable tasks
        failed_tasks = [
            {"id": t.id, "title": t.title, "assignee": t.assignee}
            for t in tasks
            if t.status == TaskStatus.FAILED
        ]
        pending_approvals = [
            {"id": t.id, "title": t.title, "assignee": t.assignee}
            for t in tasks
            if t.status == TaskStatus.NEEDS_APPROVAL
        ]

        # Stale detection placeholder — in future, compare updated_at to now
        stale_tasks: list[dict] = []

        # Cron summary
        crons = self._crons.list_all()

        return {
            "current_time": now.isoformat(),
            "board_summary": {
                "total_tasks": len(tasks),
                "backlog": status_counts.get("backlog", 0),
                "queued": status_counts.get("queued", 0),
                "in_progress": status_counts.get("in_progress", 0),
                "needs_approval": status_counts.get("needs_approval", 0),
                "done": status_counts.get("done", 0),
                "failed": status_counts.get("failed", 0),
            },
            "failed_tasks": failed_tasks,
            "pending_approvals": pending_approvals,
            "stale_tasks": stale_tasks,
            "cron_summary": {
                "total_crons": len(crons),
            },
            "memories": memories,
        }

    def gather_as_message(self) -> str:
        """Gather context and format as a message (sync, no memories)."""
        ctx = self.gather()
        return self._format_message(ctx)

    async def gather_as_message_async(self) -> str:
        """Gather context with memories and format as a message."""
        ctx = await self.gather_async()
        return self._format_message(ctx)

    def _format_message(self, ctx: dict) -> str:
        """Format a context dict into a message for the orchestrator."""
        parts = [
            "## Heartbeat Wake Cycle",
            "",
            f"**Time:** {ctx['current_time']}",
            "",
            "### Board Summary",
            f"- Total tasks: {ctx['board_summary']['total_tasks']}",
            f"- Backlog: {ctx['board_summary']['backlog']}",
            f"- Queued: {ctx['board_summary']['queued']}",
            f"- In progress: {ctx['board_summary']['in_progress']}",
            f"- Needs approval: {ctx['board_summary']['needs_approval']}",
            f"- Done: {ctx['board_summary']['done']}",
            f"- Failed: {ctx['board_summary']['failed']}",
        ]

        if ctx["failed_tasks"]:
            parts.append("")
            parts.append("### Failed Tasks (need retry or attention)")
            for ft in ctx["failed_tasks"]:
                parts.append(
                    f"- [{ft['id']}] {ft['title']} (assignee: {ft['assignee']})"
                )

        if ctx["pending_approvals"]:
            parts.append("")
            parts.append("### Pending Approvals")
            for pa in ctx["pending_approvals"]:
                parts.append(
                    f"- [{pa['id']}] {pa['title']} (assignee: {pa['assignee']})"
                )

        if ctx["stale_tasks"]:
            parts.append("")
            parts.append("### Stale Tasks (stuck too long)")
            for st in ctx["stale_tasks"]:
                parts.append(
                    f"- [{st['id']}] {st['title']} (assignee: {st['assignee']})"
                )

        parts.append("")
        parts.append(f"### Crons: {ctx['cron_summary']['total_crons']} defined")

        if ctx["memories"]:
            parts.append("")
            parts.append("### Relevant Memories")
            for m in ctx["memories"]:
                fact = m.fact if hasattr(m, "fact") else str(m)
                parts.append(f"- {fact}")

        parts.append("")
        parts.append(
            "Based on this context, decide what actions to take. Options:\n"
            "1. Create tasks on the board for agents to handle\n"
            "2. Retry failed tasks\n"
            "3. Notify the user about items needing attention\n"
            "4. Do nothing if all is quiet\n"
            "\n"
            "Respond with your reasoning and any actions you want to take."
        )

        return "\n".join(parts)
