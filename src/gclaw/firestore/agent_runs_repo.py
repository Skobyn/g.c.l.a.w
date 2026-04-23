"""Firestore repo for live agent-run status.

Two write surfaces, both under ``users/{user_id}/agent_runs``:

* **Session doc** at ``.../agent_runs/{session_id}`` — rolling
  "current activity" snapshot. Merge-upsert on every AGENT span;
  later spans overwrite earlier ones. Good for the NowPlayingCard
  (which agent is speaking right now, which model, active tool).

* **Turn sub-collection** at ``.../agent_runs/{session_id}/turns/{trace_id}``
  — one doc per distinct chat turn (keyed by the root span's
  trace_id). Merge-upsert on every span within that turn so tokens
  accumulate in-place. Preserves turn-level history so the session
  timeline UI can list "turn 1: 4611 in / 6 out / $0.001", etc.

Session-level aggregates (total tokens, cost, turn count) are
computed client-side in the UI by summing across the turn
sub-collection. Keeps the write path dumb; reads are cheap because
turn docs are bounded (1 per chat message).

Write-only from the backend; reads happen on the frontend via
``onSnapshot`` for the live /admin/live dashboard.
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
        """Merge the given span-end event into:

        1. The session doc at ``agent_runs/{session_id}`` (rolling
           "current activity" snapshot).
        2. The per-turn doc at
           ``agent_runs/{session_id}/turns/{trace_id}`` — same shape
           but scoped to one chat turn so the UI timeline can list
           each turn's model / tokens / cost independently.

        Fail-soft: any Firestore error is logged and swallowed so the
        span emission path never blocks on the dashboard write.
        """
        if not user_id or not run_id or self._db is None:
            return
        data = event.get("data") or {}
        trace_id = data.get("trace_id")
        now_iso = datetime.now(timezone.utc).isoformat()

        payload: dict[str, Any] = {
            "run_id": run_id,
            "user_id": user_id,
            "active_agent": data.get("agent"),
            "model_id": data.get("model_id"),
            "provider": data.get("provider"),
            "tokens": data.get("tokens") or {},
            "status": data.get("status"),
            "last_span_id": data.get("span_id"),
            "last_trace_id": trace_id,
            "updated_at": now_iso,
        }
        # Strip None so Firestore doesn't overwrite existing values with nulls.
        clean = {k: v for k, v in payload.items() if v is not None}
        session_ref = (
            self._db.collection("users")
            .document(user_id)
            .collection("agent_runs")
            .document(run_id)
        )
        try:
            session_ref.set(clean, merge=True)
        except Exception:
            logger.warning(
                "agent_runs: session upsert failed for user=%s run=%s",
                user_id,
                run_id,
                exc_info=True,
            )

        if not trace_id:
            return

        # Per-turn doc. started_at is written only on first upsert (via
        # merge semantics: once set, subsequent writes keep the
        # earliest value by NOT including started_at in later payloads).
        turn_payload = {
            **clean,
            "turn_id": trace_id,
            "updated_at": now_iso,
        }
        try:
            turn_ref = session_ref.collection("turns").document(trace_id)
            existing = turn_ref.get()
            if not getattr(existing, "exists", False):
                turn_payload["started_at"] = now_iso
            turn_ref.set(turn_payload, merge=True)
        except Exception:
            logger.warning(
                "agent_runs: turn upsert failed for user=%s run=%s trace=%s",
                user_id,
                run_id,
                trace_id,
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
