"""Typed Firestore repo for cron-generated system events awaiting the
next heartbeat tick.

Collection path: ``users/{userId}/cron_event_queue/{autoId}``

Each doc is ``{assignee: str, text: str, queued_at: datetime, cron_id?:
str}``. The heartbeat service drains pending entries for an agent at the
top of each tick and prepends their text to the context message.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class CronEventQueueRepo:
    """Synchronous Firestore repository for queued cron system events."""

    def __init__(self, db: Any, user_id: str) -> None:
        self._db = db
        self._user_id = user_id

    def _collection_ref(self):
        return (
            self._db.collection("users")
            .document(self._user_id)
            .collection("cron_event_queue")
        )

    def enqueue(
        self,
        assignee: str,
        text: str,
        *,
        cron_id: str | None = None,
    ) -> str:
        """Write a new pending event and return its auto-generated id."""
        col = self._collection_ref()
        ref = col.document()
        doc: dict = {
            "assignee": assignee,
            "text": text,
            "queued_at": datetime.now(timezone.utc),
        }
        if cron_id is not None:
            doc["cron_id"] = cron_id
        ref.set(doc)
        return ref.id

    def list_pending(self, assignee: str) -> list[dict]:
        """Return ``[{id, text, queued_at, ...}]`` for all pending events
        targeting ``assignee``.

        Events already marked ``drained=True`` are excluded. No ordering
        guarantees beyond Firestore's default (we only need the whole set
        per tick).
        """
        col = self._collection_ref()
        docs = col.where("assignee", "==", assignee).stream()
        out: list[dict] = []
        for snap in docs:
            data = snap.to_dict() or {}
            if data.get("drained") is True:
                continue
            data["id"] = snap.id
            out.append(data)
        return out

    def mark_drained(self, doc_ids: list[str]) -> None:
        """Remove the given events from the pending queue.

        Implemented as delete — once a heartbeat has consumed the event,
        there's no reason to retain a tombstone. Errors on individual
        docs are swallowed so one bad id can't strand the rest.
        """
        if not doc_ids:
            return
        col = self._collection_ref()
        for doc_id in doc_ids:
            try:
                col.document(doc_id).delete()
            except Exception:
                # Best-effort drain; the next tick will retry.
                continue
