"""Firestore repo for live agent-run status.

Collection path: ``users/{user_id}/agent_runs/{run_id}``

Write-only from the backend; reads happen on the frontend via
``onSnapshot`` for the live /admin/live dashboard. Each write is a
merge-upsert — there's no history here, just current state.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class AgentRunsRepo:
    """Merge-upserts agent-run summaries for the live dashboard."""

    def __init__(self, db: Any) -> None:
        self._db = db

    def upsert(
        self,
        *,
        user_id: str,
        run_id: str,
        event: dict[str, Any],
    ) -> None:
        """Merge the given span-end event into the run doc.

        Fail-soft: any Firestore error is logged and swallowed so the
        span emission path never blocks on the dashboard write.
        """
        if not user_id or not run_id or self._db is None:
            return
        data = event.get("data") or {}
        payload: dict[str, Any] = {
            "run_id": run_id,
            "user_id": user_id,
            "active_agent": data.get("agent"),
            "model_id": data.get("model_id"),
            "tokens": data.get("tokens") or {},
            "status": data.get("status"),
            "last_span_id": data.get("span_id"),
            "last_trace_id": data.get("trace_id"),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        # Strip None so Firestore doesn't overwrite existing values with nulls.
        clean = {k: v for k, v in payload.items() if v is not None}
        try:
            (
                self._db.collection("users")
                .document(user_id)
                .collection("agent_runs")
                .document(run_id)
                .set(clean, merge=True)
            )
        except Exception:
            logger.warning(
                "agent_runs: upsert failed for user=%s run=%s",
                user_id,
                run_id,
                exc_info=True,
            )

    def get_owner(self, run_id: str, user_id: str) -> bool:
        """True when ``user_id`` owns ``run_id`` (doc exists under that user).

        Used by the SSE endpoint to reject cross-user subscriptions.
        """
        if not user_id or not run_id or self._db is None:
            return False
        try:
            doc = (
                self._db.collection("users")
                .document(user_id)
                .collection("agent_runs")
                .document(run_id)
                .get()
            )
            return bool(getattr(doc, "exists", False))
        except Exception:
            logger.warning(
                "agent_runs: get_owner failed", exc_info=True
            )
            return False
