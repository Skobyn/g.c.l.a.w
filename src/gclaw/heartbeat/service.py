"""Heartbeat service — the orchestrator's consciousness loop.

The heartbeat is NOT a health monitor. It is the mechanism that makes
each agent proactive. On each cycle:

1. Drain any queued cron system events for this agent.
2. Gather context (board state, crons, time, memories).
3. Gate: skip entirely if outside active-hours, or if there's nothing
   to do and this wasn't a manual trigger.
4. Build the agent message (with the HEARTBEAT_OK protocol appended).
5. Run the agent under a per-config timeout.
6. Parse the reply — if the agent returned the bare HEARTBEAT_OK token
   (optionally followed by a short ack), status is OK_TOKEN and we skip
   the heavy post-work. Otherwise we log, consolidate memory, and sweep
   stale sessions.
7. Emit a HeartbeatEvent on the bus for the admin dashboard.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from gclaw.dispatch.runner import AgentRunner
from gclaw.heartbeat.context import HeartbeatContextGatherer
from gclaw.heartbeat.events import (
    HeartbeatEvent,
    HeartbeatStatus,
    get_event_bus,
)
from gclaw.heartbeat.log import HeartbeatLog, HeartbeatLogRepo
from gclaw.heartbeat.reason import WakeReason
from gclaw.heartbeat.schedule import is_within_active_hours

if TYPE_CHECKING:
    from gclaw.firestore.cron_event_queue_repo import CronEventQueueRepo
    from gclaw.heartbeat.config import HeartbeatConfig
    from gclaw.memory.consolidation import MemoryConsolidator
    from gclaw.session.service import SessionService

logger = logging.getLogger(__name__)


_OK_TOKEN = "HEARTBEAT_OK"
_OK_RE = re.compile(r"^\s*HEARTBEAT_OK\b[ \t:,-]*(.*)$", re.DOTALL)


class HeartbeatService:
    """Runs a single heartbeat cycle."""

    def __init__(
        self,
        context_gatherer: HeartbeatContextGatherer,
        agent_runner: AgentRunner,
        log_repo: HeartbeatLogRepo,
        user_id: str,
        session_id: str = "heartbeat",
        consolidator: "MemoryConsolidator | None" = None,
        session_store: "SessionService | None" = None,
        stale_session_threshold_seconds: int = 3600,
        # NEW — per-agent overhaul
        agent_name: str = "orchestrator",
        heartbeat_config: "HeartbeatConfig | None" = None,
        cron_event_queue_repo: "CronEventQueueRepo | None" = None,
    ) -> None:
        self._gatherer = context_gatherer
        self._runner = agent_runner
        self._log_repo = log_repo
        self._user_id = user_id
        self._session_id = session_id
        self._consolidator = consolidator
        self._session_store = session_store
        self._stale_session_threshold_seconds = stale_session_threshold_seconds
        self._agent_name = agent_name
        self._config = heartbeat_config
        self._cron_queue_repo = cron_event_queue_repo

    async def run(self, reason: WakeReason = WakeReason.INTERVAL) -> dict:
        """Execute one heartbeat cycle.

        Returns a dict with:
        - orchestrator_response: the agent's text response (may be empty
          on OK_TOKEN / OK_EMPTY / SKIPPED)
        - actions_taken: list of tool calls the agent made
        - context: the raw context dict
        - status: the terminal HeartbeatStatus for this cycle
        """
        t0 = time.time()
        bus = get_event_bus()
        agent_id = self._agent_name or self._user_id or "orchestrator"

        try:
            # 1. Drain cron event queue for this agent.
            drained_events, drained_ids = self._drain_cron_events()
            effective_reason = reason
            if drained_events and reason == WakeReason.INTERVAL:
                effective_reason = WakeReason.CRON

            # 2. Gate: active-hours window.
            if self._config is not None and self._config.active_hours:
                now_local = datetime.now(timezone.utc)
                if not is_within_active_hours(
                    now_local, self._config.active_hours
                ):
                    bus.emit(
                        HeartbeatEvent(
                            agent_id=agent_id,
                            status=HeartbeatStatus.SKIPPED,
                            reason=effective_reason,
                            duration_ms=int((time.time() - t0) * 1000),
                            preview="outside active_hours",
                        )
                    )
                    return {
                        "orchestrator_response": "",
                        "actions_taken": [],
                        "tasks_created": [],
                        "context": {},
                        "status": HeartbeatStatus.SKIPPED,
                    }

            # 3. Gather context.
            context = self._gatherer.gather()
            base_message = self._gatherer.gather_as_message()

            # 4. Empty-input gate — only when a per-agent config is
            #    wired (preserves legacy behaviour for the default call
            #    site) and this is an interval tick (manual triggers
            #    always run, cron drains obviously have something to
            #    say).
            if (
                self._config is not None
                and not drained_events
                and effective_reason
                not in (WakeReason.MANUAL, WakeReason.CRON)
                and self._is_board_empty(context)
            ):
                bus.emit(
                    HeartbeatEvent(
                        agent_id=agent_id,
                        status=HeartbeatStatus.OK_EMPTY,
                        reason=effective_reason,
                        duration_ms=int((time.time() - t0) * 1000),
                        preview="nothing to do",
                    )
                )
                return {
                    "orchestrator_response": "",
                    "actions_taken": [],
                    "tasks_created": [],
                    "context": context,
                    "status": HeartbeatStatus.OK_EMPTY,
                }

            # 5. Build the agent message — prepend drained events, append
            #    the HEARTBEAT_OK protocol instruction.
            message = self._build_message(base_message, drained_events)

            # 6. Run agent under per-config timeout.
            timeout_s = self._config.timeout_seconds if self._config else 120
            response = await asyncio.wait_for(
                self._runner.run(
                    user_id=self._user_id,
                    session_id=self._session_id,
                    message=message,
                ),
                timeout=timeout_s,
            )

            # 7. Parse reply for the HEARTBEAT_OK sentinel.
            ack_max = self._config.ack_max_chars if self._config else 30
            is_ok_token, ack_body = self._parse_ok_token(
                response.text or "", ack_max
            )

            actions_taken = [
                f"{tc['name']}({tc['args']})" for tc in response.tool_calls
            ]
            tasks_created = [
                tc["args"].get("title", "unknown")
                for tc in response.tool_calls
                if tc["name"] == "create_board_task"
            ]

            if is_ok_token and not actions_taken:
                # Nothing to record — mark drained and emit OK_TOKEN.
                self._finalize_drain(drained_ids)
                bus.emit(
                    HeartbeatEvent(
                        agent_id=agent_id,
                        status=HeartbeatStatus.OK_TOKEN,
                        reason=effective_reason,
                        duration_ms=int((time.time() - t0) * 1000),
                        preview=(ack_body or _OK_TOKEN)[:100],
                    )
                )
                return {
                    "orchestrator_response": response.text,
                    "actions_taken": [],
                    "tasks_created": [],
                    "context": context,
                    "status": HeartbeatStatus.OK_TOKEN,
                }

            # 8. Full reply — SENT: log, consolidate, sweep, drain.
            summary = self._build_context_summary(context)
            log = HeartbeatLog(
                context_summary=summary,
                reasoning=response.text,
                actions_taken=actions_taken,
                tasks_created=tasks_created,
            )
            self._log_repo.save(log)

            if (
                self._consolidator is not None
                and context.get("board_summary", {}).get("in_progress", 0) == 0
            ):
                try:
                    consolidation = await self._consolidator.run(
                        user_id=self._user_id
                    )
                    logger.info(
                        "Memory consolidation: scanned=%d pruned=%d merged=%d",
                        consolidation.memories_scanned,
                        consolidation.memories_pruned,
                        consolidation.memories_merged,
                    )
                except Exception:
                    logger.warning(
                        "Memory consolidation failed", exc_info=True
                    )

            if self._session_store is not None:
                await self._auto_end_stale_sessions()

            self._finalize_drain(drained_ids)

            bus.emit(
                HeartbeatEvent(
                    agent_id=agent_id,
                    status=HeartbeatStatus.SENT,
                    reason=effective_reason,
                    duration_ms=int((time.time() - t0) * 1000),
                    preview=(response.text or "")[:100],
                )
            )

            return {
                "orchestrator_response": response.text,
                "actions_taken": actions_taken,
                "tasks_created": tasks_created,
                "context": context,
                "status": HeartbeatStatus.SENT,
            }
        except Exception as e:
            bus.emit(
                HeartbeatEvent(
                    agent_id=agent_id,
                    status=HeartbeatStatus.FAILED,
                    reason=reason,
                    duration_ms=int((time.time() - t0) * 1000),
                    error=str(e),
                )
            )
            raise

    # ------------------------------------------------------------------ helpers

    def _drain_cron_events(self) -> tuple[list[dict], list[str]]:
        """Fetch pending cron system events for this agent.

        Returns ``(events, ids)``. Events are *not* yet marked drained —
        that happens after the agent has successfully consumed them, to
        avoid losing an event if the run blows up mid-flight.
        """
        if self._cron_queue_repo is None:
            return [], []
        try:
            events = self._cron_queue_repo.list_pending(self._agent_name)
        except Exception:
            logger.warning(
                "Failed to read cron event queue for agent %s",
                self._agent_name,
                exc_info=True,
            )
            return [], []
        ids = [e["id"] for e in events if e.get("id")]
        return events, ids

    def _finalize_drain(self, doc_ids: list[str]) -> None:
        if not doc_ids or self._cron_queue_repo is None:
            return
        try:
            self._cron_queue_repo.mark_drained(doc_ids)
        except Exception:
            logger.warning(
                "Failed to mark cron events drained (ids=%s)",
                doc_ids,
                exc_info=True,
            )

    def _build_message(
        self, base_message: str, drained_events: list[dict]
    ) -> str:
        parts: list[str] = []
        if drained_events:
            parts.append("## Queued System Events")
            for ev in drained_events:
                parts.append(f"- {ev.get('text', '')}")
            parts.append("")
        parts.append(base_message)
        ack_max = self._config.ack_max_chars if self._config else 30
        parts.append("")
        parts.append("---")
        parts.append(
            "If nothing requires action, reply with the literal token "
            f"{_OK_TOKEN} (optionally followed by \u2264{ack_max} chars of "
            "context). Otherwise respond normally."
        )
        return "\n".join(parts)

    @staticmethod
    def _is_board_empty(context: dict) -> bool:
        bs = context.get("board_summary") or {}
        counts = (
            bs.get("failed", 0),
            bs.get("needs_approval", 0),
            bs.get("queued", 0),
            bs.get("in_progress", 0),
        )
        return all(c == 0 for c in counts)

    @staticmethod
    def _parse_ok_token(text: str, ack_max: int) -> tuple[bool, str]:
        """Return ``(is_ok_token, ack_body)``.

        ``is_ok_token`` is True when the reply starts with the
        ``HEARTBEAT_OK`` sentinel and any trailing text fits inside
        ``ack_max`` characters (whitespace stripped).
        """
        if not text:
            return False, ""
        m = _OK_RE.match(text.strip())
        if not m:
            return False, ""
        tail = m.group(1).strip()
        if len(tail) > ack_max:
            return False, tail
        return True, tail

    async def _auto_end_stale_sessions(self) -> None:
        """Find sessions idle for longer than the threshold and end them.

        Never raises — an auto-end failure must not break the heartbeat
        tick. The heartbeat session itself is excluded from the sweep by
        its session_id.
        """
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(
                seconds=self._stale_session_threshold_seconds
            )
            stale = self._session_store.list_active_older_than(cutoff)
            for sess in stale:
                if sess.id == self._session_id:
                    continue
                try:
                    await self._session_store.end_session(sess.id)
                    logger.info(
                        "auto-ended stale session %s (idle since %s)",
                        sess.id,
                        sess.updated_at.isoformat(),
                    )
                except Exception:
                    logger.warning(
                        "auto-end failed for session %s",
                        sess.id,
                        exc_info=True,
                    )
        except Exception:
            logger.warning("auto-end sweep failed", exc_info=True)

    def _build_context_summary(self, context: dict) -> str:
        """Build a concise summary string from the context dict."""
        bs = context["board_summary"]
        parts = [
            f"{bs['total_tasks']} tasks on board",
            f"({bs['queued']} queued, {bs['in_progress']} in progress, "
            f"{bs['failed']} failed, {bs['needs_approval']} needs approval)",
        ]
        return " ".join(parts)
