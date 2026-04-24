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


def _coerce_iso(value: Any) -> str | None:
    """Return an ISO-8601 string for a datetime / Firestore Timestamp /
    already-string field. Used by the list_* APIs so the JSON response
    has a consistent string shape regardless of how the doc was
    written."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    to_iso = getattr(value, "isoformat", None)
    if callable(to_iso):
        try:
            return to_iso()
        except Exception:
            pass
    to_date = getattr(value, "to_datetime", None) or getattr(value, "ToDatetime", None)
    if callable(to_date):
        try:
            return to_date().isoformat()
        except Exception:
            pass
    return str(value)


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

        span_cost = data.get("cost_usd")
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

        # Session-level cost accumulator: atomically add the span's
        # cost so the Observability page can show running session
        # totals without the UI having to sum across turns. Uses
        # FieldValue.Increment to stay correct under concurrent writes.
        session_update = dict(clean)
        if span_cost is not None:
            try:
                from google.cloud.firestore_v1 import Increment
                session_update["cost_usd_session"] = Increment(float(span_cost))
            except Exception:
                # google-cloud-firestore not importable in some unit-
                # test environments — fall back to a plain set.
                pass

        try:
            session_ref.set(session_update, merge=True)
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
        if span_cost is not None:
            try:
                from google.cloud.firestore_v1 import Increment
                turn_payload["cost_usd_turn"] = Increment(float(span_cost))
            except Exception:
                pass
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

    def append_messages(
        self,
        *,
        user_id: str,
        run_id: str,
        trace_id: str,
        messages: list[dict[str, Any]],
    ) -> None:
        """Append per-author messages for a turn.

        Writes each message as its own doc under
        ``users/{uid}/agent_runs/{run_id}/turns/{trace_id}/messages/{seq}``
        so the UI can subscribe via ``onSnapshot`` and render an
        author-attributed transcript of the turn (user prompt →
        orchestrator output → research-mgr output → ...).

        Caller is responsible for redacting message content before
        passing it in — this repo writes the bytes verbatim.

        Sequencing: docs are keyed by zero-padded index ``seq`` so
        Firestore lexical ordering matches insertion order without
        needing a separate ``order_by`` index.

        Fail-soft: any Firestore error is logged and swallowed.
        """
        if (
            not user_id
            or not run_id
            or not trace_id
            or not messages
            or self._db is None
        ):
            return
        try:
            turn_ref = (
                self._db.collection("users")
                .document(user_id)
                .collection("agent_runs")
                .document(run_id)
                .collection("turns")
                .document(trace_id)
            )
            now_iso = datetime.now(timezone.utc).isoformat()
            # Batch the writes so a turn with N authors is one round-trip.
            batch = self._db.batch()
            for idx, msg in enumerate(messages):
                doc_id = f"{idx:04d}"
                payload = {
                    "seq": idx,
                    "ts": now_iso,
                    **msg,
                }
                doc_ref = turn_ref.collection("messages").document(doc_id)
                batch.set(doc_ref, payload, merge=False)
            batch.commit()
        except Exception:
            logger.warning(
                "agent_runs: append_messages failed for user=%s run=%s trace=%s",
                user_id,
                run_id,
                trace_id,
                exc_info=True,
            )

    # ── List APIs (powering the Observability page when the web
    #    client doesn't have Firebase configured for direct
    #    onSnapshot access — i.e. NEXT_PUBLIC_DEV_BYPASS_AUTH=true
    #    builds). All methods are best-effort and return [] on error.

    def list_recent_runs(self, *, user_id: str, limit: int = 20) -> list[dict]:
        """Return up to ``limit`` recent agent_runs docs for a user.

        Sorted by ``updated_at`` descending. Falls back to client-side
        sort because some legacy docs may not have ``updated_at``.
        """
        if not user_id or self._db is None:
            return []
        try:
            col = (
                self._db.collection("users")
                .document(user_id)
                .collection("agent_runs")
            )
            docs = list(col.stream())
        except Exception:
            logger.warning(
                "agent_runs: list_recent_runs failed for user=%s",
                user_id,
                exc_info=True,
            )
            return []

        rows: list[dict] = []
        for d in docs:
            try:
                data = d.to_dict() or {}
            except Exception:
                continue
            rows.append({
                "id": d.id,
                "active_agent": data.get("active_agent"),
                "model_id": data.get("model_id"),
                "status": data.get("status"),
                "updated_at": _coerce_iso(data.get("updated_at")),
            })
        rows.sort(
            key=lambda r: r.get("updated_at") or "",
            reverse=True,
        )
        return rows[:limit]

    def list_turns(self, *, user_id: str, run_id: str, limit: int = 50) -> list[dict]:
        """Return turn docs for a session, newest first."""
        if not user_id or not run_id or self._db is None:
            return []
        try:
            col = (
                self._db.collection("users")
                .document(user_id)
                .collection("agent_runs")
                .document(run_id)
                .collection("turns")
            )
            docs = list(col.stream())
        except Exception:
            logger.warning(
                "agent_runs: list_turns failed for user=%s run=%s",
                user_id, run_id, exc_info=True,
            )
            return []

        rows: list[dict] = []
        for d in docs:
            try:
                data = d.to_dict() or {}
            except Exception:
                continue
            rows.append({
                "id": d.id,
                "turn_id": data.get("turn_id") or d.id,
                "active_agent": data.get("active_agent"),
                "model_id": data.get("model_id"),
                "status": data.get("status"),
                "tokens": data.get("tokens"),
                "cost_usd_turn": data.get("cost_usd_turn"),
                "cost_usd_session": data.get("cost_usd_session"),
                "started_at": _coerce_iso(data.get("started_at")),
                "updated_at": _coerce_iso(data.get("updated_at")),
            })
        rows.sort(
            key=lambda r: (r.get("started_at") or r.get("updated_at") or ""),
            reverse=True,
        )
        return rows[:limit]

    def list_messages(
        self, *, user_id: str, run_id: str, trace_id: str,
    ) -> list[dict]:
        """Return per-author messages for a single turn, in seq order."""
        if not user_id or not run_id or not trace_id or self._db is None:
            return []
        try:
            col = (
                self._db.collection("users")
                .document(user_id)
                .collection("agent_runs")
                .document(run_id)
                .collection("turns")
                .document(trace_id)
                .collection("messages")
            )
            docs = list(col.stream())
        except Exception:
            logger.warning(
                "agent_runs: list_messages failed for user=%s run=%s trace=%s",
                user_id, run_id, trace_id, exc_info=True,
            )
            return []

        rows: list[dict] = []
        for d in docs:
            try:
                data = d.to_dict() or {}
            except Exception:
                continue
            rows.append({
                "seq": data.get("seq", 0),
                "ts": _coerce_iso(data.get("ts")),
                "author": data.get("author"),
                "role": data.get("role"),
                "text": data.get("text"),
                "tool_calls": data.get("tool_calls") or [],
            })
        rows.sort(key=lambda r: r.get("seq") or 0)
        return rows

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
