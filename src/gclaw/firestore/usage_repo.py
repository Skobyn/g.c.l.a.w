"""Firestore repo for unified usage telemetry events.

Collection path: users/{userId}/usage/{eventId}

Per-user scoping mirrors the session/board pattern. `user_id="system"`
is accepted for events that are not tied to a concrete end-user (e.g.
background jobs, cron heartbeats).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from google.cloud.firestore import Client as FirestoreClient

from gclaw.models.usage import UsageEvent, UsageKind


_TTL_DAYS = 90


class UsageRepo:
    """Synchronous Firestore repository for usage telemetry."""

    def __init__(
        self, db: FirestoreClient, user_id: str | None = None
    ) -> None:
        self._db = db
        self._default_user_id = user_id

    def _collection_ref(self, user_id: str | None = None):
        uid = user_id or self._default_user_id
        if uid is None:
            raise ValueError(
                "user_id required — not set at init or in method call"
            )
        return (
            self._db.collection("users")
            .document(uid)
            .collection("usage")
        )

    # -- writes ----------------------------------------------------------

    def record(
        self, event: UsageEvent, user_id: str | None = None
    ) -> UsageEvent:
        uid = user_id or event.user_id or self._default_user_id or "system"
        doc_ref = self._collection_ref(uid).document(event.id)
        data = event.to_firestore_dict()
        data["expires_at"] = event.timestamp + timedelta(days=_TTL_DAYS)
        doc_ref.set(data)
        return event

    # -- reads -----------------------------------------------------------

    def list_recent(
        self,
        limit: int = 100,
        kind: UsageKind | None = None,
        since: datetime | None = None,
        user_id: str | None = None,
    ) -> list[UsageEvent]:
        """Newest-first. Optional filters by kind and lower-bound timestamp."""
        q = self._collection_ref(user_id)
        if kind is not None:
            q = q.where("kind", "==", kind.value)
        if since is not None:
            q = q.where("timestamp", ">=", since)
        try:
            from google.cloud.firestore import Query  # type: ignore
            q = q.order_by("timestamp", direction=Query.DESCENDING)
        except Exception:
            # MagicMock or a restricted client — chainable no-op.
            q = q.order_by("timestamp")
        q = q.limit(limit)
        docs = list(q.stream())
        events = [
            UsageEvent.from_firestore_dict(d.id, d.to_dict()) for d in docs
        ]
        # Defensive in-memory sort — some fakes ignore order_by.
        events.sort(key=lambda e: e.timestamp, reverse=True)
        return events

    def aggregate_by_name(
        self,
        kind: UsageKind,
        since: datetime,
        limit: int = 20,
        user_id: str | None = None,
    ) -> list[dict]:
        """Group events by `name` and summarize.

        Firestore has no native GROUP BY — fetch matching rows and reduce
        in memory. Acceptable while per-user volume is modest (bounded by
        the 90d TTL and typical hourly rates).
        """
        q = (
            self._collection_ref(user_id)
            .where("kind", "==", kind.value)
            .where("timestamp", ">=", since)
        )
        docs = list(q.stream())
        events = [
            UsageEvent.from_firestore_dict(d.id, d.to_dict()) for d in docs
        ]

        buckets: dict[str, dict] = defaultdict(
            lambda: {
                "count": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "cost_usd": 0.0,
                "duration_ms_sum": 0,
                "failures": 0,
            }
        )
        for ev in events:
            b = buckets[ev.name]
            b["count"] += 1
            b["tokens_in"] += ev.tokens_in or 0
            b["tokens_out"] += ev.tokens_out or 0
            b["cost_usd"] += ev.cost_usd or 0.0
            b["duration_ms_sum"] += ev.duration_ms or 0
            if not ev.success:
                b["failures"] += 1

        rows: list[dict] = []
        for name, b in buckets.items():
            count = b["count"]
            rows.append({
                "name": name,
                "count": count,
                "tokens_in": b["tokens_in"],
                "tokens_out": b["tokens_out"],
                "cost_usd": round(b["cost_usd"], 6),
                "avg_duration_ms": (
                    b["duration_ms_sum"] // count if count else 0
                ),
                "failure_rate": (
                    (b["failures"] / count) if count else 0.0
                ),
            })
        rows.sort(key=lambda r: r["count"], reverse=True)
        return rows[:limit]

    def aggregate_by_hour(
        self,
        since: datetime,
        user_id: str | None = None,
    ) -> list[dict]:
        """Per-hour rollup across all kinds."""
        q = self._collection_ref(user_id).where("timestamp", ">=", since)
        docs = list(q.stream())
        events = [
            UsageEvent.from_firestore_dict(d.id, d.to_dict()) for d in docs
        ]

        buckets: dict[datetime, dict] = defaultdict(
            lambda: {
                "model_count": 0,
                "agent_count": 0,
                "skill_count": 0,
                "tool_count": 0,
                "cost_usd": 0.0,
            }
        )
        for ev in events:
            ts = ev.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            hour = ts.replace(minute=0, second=0, microsecond=0)
            b = buckets[hour]
            key = f"{ev.kind.value}_count"
            if key in b:
                b[key] += 1
            b["cost_usd"] += ev.cost_usd or 0.0

        rows = []
        for hour in sorted(buckets.keys()):
            b = buckets[hour]
            rows.append({
                "hour_iso": hour.isoformat(),
                "model_count": b["model_count"],
                "agent_count": b["agent_count"],
                "skill_count": b["skill_count"],
                "tool_count": b["tool_count"],
                "cost_usd": round(b["cost_usd"], 6),
            })
        return rows
