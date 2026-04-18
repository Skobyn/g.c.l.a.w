"""Cron service — business logic for scheduled task management."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from gclaw.board.service import BoardService
from gclaw.cron.delivery import CronDeliveryService
from gclaw.firestore.cron_repo import CronRepo
from gclaw.models.cron import (
    AgentTurnPayload,
    Cron,
    CronExprSchedule,
    CronMode,
    CronStatus,
    DeliveryAnnounce,
    DeliveryNone,
    DeliveryWebhook,
    SystemEventPayload,
)
from gclaw.models.task import TaskStatus

logger = logging.getLogger(__name__)


class CronService:
    """High-level operations on cron definitions."""

    def __init__(
        self,
        cron_repo: CronRepo,
        board_service: BoardService,
        cron_event_queue_repo: Any | None = None,
        delivery_service: CronDeliveryService | None = None,
        default_timezone: str = "UTC",
    ) -> None:
        self._repo = cron_repo
        self._board = board_service
        self._event_queue = cron_event_queue_repo
        self._delivery = delivery_service or CronDeliveryService()
        # Applied to CronExprSchedule records that come in without an
        # explicit tz. Without this, every cron silently interprets its
        # expression in UTC, so "0 8 * * *" fires at midnight for a
        # Central-time user.
        self._default_tz = default_timezone

    # ------------------------------------------------------------------ create
    def create(
        self,
        title: str,
        assignee: str,
        *,
        # Legacy-friendly shortcut: cron expression string.
        schedule: Any | None = None,
        cron_expr: str | None = None,
        payload: Any | None = None,
        delivery: Any | None = None,
        failure_alert: Any | None = None,
        mode: str = "todo",
        description: str = "",
        task_priority: str = "medium",
        wake_mode: str = "now",
        enabled: bool = True,
        delete_after_run: bool = False,
    ) -> Cron:
        """Create a cron. Accepts either structured unions or legacy kwargs.

        Shortcut behaviour:
        - If ``schedule`` is a str or ``cron_expr`` is given, it is wrapped in
          a ``CronExprSchedule``.
        - If ``payload`` is omitted, a default ``AgentTurnPayload`` is built
          from ``title``/``description``.
        - If ``delivery`` is omitted, ``DeliveryNone`` is used.
        """
        sched = self._coerce_schedule(schedule, cron_expr)
        # If the caller gave us a cron-expression schedule without a tz,
        # stamp the user default so the schedule isn't silently UTC.
        if isinstance(sched, CronExprSchedule) and not sched.tz:
            sched = sched.model_copy(update={"tz": self._default_tz})
        elif isinstance(sched, dict) and sched.get("kind") == "cron" and not sched.get("tz"):
            sched = {**sched, "tz": self._default_tz}
        pl = self._coerce_payload(payload, title=title, description=description)
        deliv = delivery if delivery is not None else DeliveryNone()

        cron = Cron(
            title=title,
            description=description,
            schedule=sched,
            payload=pl,
            delivery=deliv,
            failure_alert=failure_alert,
            mode=CronMode(mode),
            assignee=assignee,
            task_priority=task_priority,
            wake_mode=wake_mode,
            enabled=enabled,
            delete_after_run=delete_after_run,
        )
        return self._repo.create(cron)

    @staticmethod
    def _coerce_schedule(schedule: Any, cron_expr: str | None):
        if schedule is None and cron_expr is None:
            raise ValueError("create() requires 'schedule' or 'cron_expr'")
        if cron_expr is not None and schedule is None:
            return CronExprSchedule(expr=cron_expr)
        if isinstance(schedule, str):
            return CronExprSchedule(expr=schedule)
        if isinstance(schedule, dict):
            # Let pydantic route via discriminator when set on Cron.
            return schedule
        return schedule

    @staticmethod
    def _coerce_payload(payload: Any, *, title: str, description: str):
        if payload is None:
            return AgentTurnPayload(message=description or title)
        if isinstance(payload, dict):
            return payload
        return payload

    # ------------------------------------------------------------------ update
    def update(
        self,
        cron_id: str,
        title: str | None = None,
        schedule: Any | None = None,
        mode: str | None = None,
        description: str | None = None,
        assignee: str | None = None,
        task_priority: str | None = None,
        payload: Any | None = None,
        delivery: Any | None = None,
        failure_alert: Any | None = None,
        wake_mode: str | None = None,
        enabled: bool | None = None,
        delete_after_run: bool | None = None,
    ) -> Cron:
        cron = self._repo.get(cron_id)
        if cron is None:
            raise ValueError(f"Cron {cron_id} not found")

        updates: dict = {}
        if title is not None:
            updates["title"] = title
        if schedule is not None:
            updates["schedule"] = (
                CronExprSchedule(expr=schedule)
                if isinstance(schedule, str)
                else schedule
            )
        if mode is not None:
            updates["mode"] = CronMode(mode)
        if description is not None:
            updates["description"] = description
        if assignee is not None:
            updates["assignee"] = assignee
        if task_priority is not None:
            updates["task_priority"] = task_priority
        if payload is not None:
            updates["payload"] = payload
        if delivery is not None:
            updates["delivery"] = delivery
        if failure_alert is not None:
            updates["failure_alert"] = failure_alert
        if wake_mode is not None:
            updates["wake_mode"] = wake_mode
        if enabled is not None:
            updates["enabled"] = enabled
            updates["status"] = (
                CronStatus.ACTIVE if enabled else CronStatus.PAUSED
            )
        if delete_after_run is not None:
            updates["delete_after_run"] = delete_after_run

        updated = cron.model_copy(update=updates)
        return self._repo.update(updated)

    def delete(self, cron_id: str) -> None:
        self._repo.delete(cron_id)

    def list_all(self) -> list[Cron]:
        return self._repo.list_all()

    def pause(self, cron_id: str) -> Cron:
        cron = self._repo.get(cron_id)
        if cron is None:
            raise ValueError(f"Cron {cron_id} not found")
        paused = cron.model_copy(
            update={"status": CronStatus.PAUSED, "enabled": False}
        )
        return self._repo.update(paused)

    def resume(self, cron_id: str) -> Cron:
        cron = self._repo.get(cron_id)
        if cron is None:
            raise ValueError(f"Cron {cron_id} not found")
        resumed = cron.model_copy(
            update={"status": CronStatus.ACTIVE, "enabled": True}
        )
        return self._repo.update(resumed)

    # ----------------------------------------------------------------- execute
    async def execute(self, cron_id: str):
        """Execute a cron based on its payload kind.

        Returns:
            - BoardTask when payload is ``agent_turn``
            - dict placeholder when payload is ``system_event`` and
              wake_mode is ``next-heartbeat``
            - None when payload is ``system_event`` and wake_mode is ``now``

        On success, dispatches the configured delivery (announce/webhook).
        On failure, increments consecutive_errors, persists the error,
        fires a failure_alert if threshold+cooldown allow, and re-raises
        the original exception.
        """
        cron = self._repo.get(cron_id)
        if cron is None:
            raise ValueError(f"Cron {cron_id} not found")
        if not cron.enabled or cron.status == CronStatus.PAUSED:
            raise ValueError(
                f"Cron {cron_id} is paused — resume it before executing"
            )

        try:
            result = self._dispatch(cron)
        except Exception as exc:
            await self._handle_failure(cron, str(exc))
            raise

        # Success bookkeeping
        updated = cron.record_run()
        self._repo.update(updated)

        # Deliver success side-effects. Use the updated cron so last_run
        # is populated in webhook payloads.
        summary = self._success_summary(updated, result)
        try:
            await self._delivery.deliver_success(updated, summary=summary)
        except Exception:
            logger.exception(
                "delivery.deliver_success raised for cron %s", cron.id
            )

        if cron.delete_after_run:
            try:
                self._repo.delete(cron.id)
            except Exception:
                logger.exception(
                    "Failed to delete one-shot cron %s", cron.id
                )

        return result

    @staticmethod
    def _success_summary(cron: Cron, result: Any) -> str:
        """Build a short human-readable success summary from the result."""
        if result is None:
            return "event dispatched"
        # BoardTask has an ``id`` attribute; system_event result is a dict
        # with cron_id/text fields.
        task_id = getattr(result, "id", None)
        if task_id is not None:
            return f"task {task_id} created"
        if isinstance(result, dict):
            return "event queued"
        return "ok"

    # -------------------------------------------------------------- internals
    def _dispatch(self, cron: Cron):
        payload = cron.payload

        if isinstance(payload, SystemEventPayload):
            if cron.wake_mode == "next-heartbeat":
                return self._enqueue_system_event(cron, payload)
            # wake_mode == "now" + system_event has no first-class handler
            # yet; a follow-up commit will wire direct heartbeat triggers.
            logger.warning(
                "cron %s: wake_mode=now with system_event payload is not "
                "yet supported — treating as no-op",
                cron.id,
            )
            return None

        if isinstance(payload, AgentTurnPayload):
            return self._create_agent_turn_task(cron, payload)

        raise ValueError(f"Unknown payload kind on cron {cron.id}")

    def _create_agent_turn_task(
        self, cron: Cron, payload: AgentTurnPayload
    ):
        if cron.mode == CronMode.AUTO:
            task_status = TaskStatus.QUEUED
        else:
            task_status = TaskStatus.BACKLOG

        return self._board.create_task(
            title=cron.title,
            assignee=cron.assignee,
            description=payload.message,
            priority=cron.task_priority,
            source_type="cron",
            source_origin=cron.id,
            status=task_status,
        )

    def _enqueue_system_event(
        self, cron: Cron, payload: SystemEventPayload
    ) -> dict:
        """Drop a placeholder event for the next heartbeat to pick up.

        Writes to ``users/{user_id}/cron_event_queue/{auto_id}``. The
        heartbeat service (follow-up commit) will drain this queue.
        """
        doc: dict = {
            "assignee": cron.assignee,
            "text": payload.text,
            "cron_id": cron.id,
            "queued_at": datetime.now(timezone.utc),
        }

        if self._event_queue is not None:
            try:
                doc["id"] = self._event_queue.enqueue(
                    assignee=cron.assignee,
                    text=payload.text,
                    cron_id=cron.id,
                )
            except Exception:
                logger.exception(
                    "Failed to enqueue system_event for cron %s via repo",
                    cron.id,
                )
            return doc

        # Fallback — direct Firestore write using CronRepo's handle.
        db = self._repo._db
        user_id = self._repo._user_id
        try:
            col = (
                db.collection("users")
                .document(user_id)
                .collection("cron_event_queue")
            )
            new_ref = col.document()
            new_ref.set(doc)
            doc["id"] = new_ref.id
        except Exception:
            logger.exception(
                "Failed to enqueue system_event for cron %s", cron.id
            )
        return doc

    async def _handle_failure(self, cron: Cron, error: str) -> None:
        updated = cron.record_failure(error)
        self._repo.update(updated)

        # Dispatch real failure alert through the delivery service, which
        # handles the threshold + cooldown checks itself. It returns True
        # when an alert was actually sent — bump last_alert_at and persist.
        try:
            sent = await self._delivery.deliver_failure_alert(
                updated, error=error
            )
        except Exception:
            logger.exception(
                "delivery.deliver_failure_alert raised for cron %s", cron.id
            )
            sent = False

        if sent:
            now = datetime.now(timezone.utc)
            alerted = updated.model_copy(
                update={"last_alert_at": now, "updated_at": now}
            )
            try:
                self._repo.update(alerted)
            except Exception:
                logger.exception(
                    "Failed to persist last_alert_at for cron %s", cron.id
                )

        # Legacy log breadcrumb — kept for humans scanning stderr.
        deliv = cron.delivery
        if isinstance(deliv, DeliveryAnnounce):
            logger.error(
                "cron %s failure (announce ch=%s to=%s): %s",
                cron.id, deliv.channel, deliv.to, error,
            )
        elif isinstance(deliv, DeliveryWebhook):
            logger.error(
                "cron %s failure (webhook url=%s): %s",
                cron.id, deliv.url, error,
            )
        else:
            logger.error("cron %s failed: %s", cron.id, error)
