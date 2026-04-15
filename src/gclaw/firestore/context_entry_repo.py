"""Firestore repo for shared-context entries.

Collection: shared_context/items/{entry_id}. System-wide (not per-user)
because agents across users share curated knowledge.
"""

from __future__ import annotations

from datetime import datetime, timezone

from google.cloud.firestore import Client as FirestoreClient

from gclaw.models.context_entry import ContextEntry


def _coerce_dt(value) -> datetime | None:
    """Accept either a datetime or ISO-8601 string.

    Real Firestore returns datetimes directly, but to_firestore_dict()
    emits ISO strings via ``model_dump(mode="json")``; this keeps the
    repo robust across both shapes.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            s = value.replace("Z", "+00:00")
            return datetime.fromisoformat(s)
        except ValueError:
            return None
    return None


def _root_doc(db: FirestoreClient):
    return db.collection("shared_context").document("items")


class ContextEntryRepo:
    def __init__(self, db: FirestoreClient) -> None:
        self._db = db

    def _collection_ref(self):
        return _root_doc(self._db).collection("entries")

    def create(self, entry: ContextEntry) -> ContextEntry:
        doc_ref = self._collection_ref().document(entry.id)
        doc_ref.set(entry.to_firestore_dict())
        return entry

    def get(self, entry_id: str) -> ContextEntry | None:
        doc = self._collection_ref().document(entry_id).get()
        if not doc.exists:
            return None
        return ContextEntry.from_firestore_dict(doc.id, doc.to_dict())

    def delete(self, entry_id: str) -> None:
        self._collection_ref().document(entry_id).delete()

    def list_by_namespace(
        self,
        namespace: str,
        limit: int = 20,
        since: datetime | None = None,
    ) -> list[ContextEntry]:
        query = self._collection_ref().where("namespace", "==", namespace)
        entries = [
            ContextEntry.from_firestore_dict(d.id, d.to_dict())
            for d in query.stream()
        ]
        if since is not None:
            entries = [e for e in entries if e.timestamp >= since]
        entries.sort(key=lambda e: e.timestamp, reverse=True)
        if limit is not None and limit > 0:
            entries = entries[:limit]
        return entries

    def latest_in(self, namespace: str) -> ContextEntry | None:
        items = self.list_by_namespace(namespace, limit=1)
        return items[0] if items else None

    def list_namespaces(self) -> list[dict]:
        """Return [{namespace, count, latest_at}] across all entries.

        In-memory aggregation — fine for the entry volumes we expect at
        this stage. Swap for a summary doc if it ever gets hot.
        """
        buckets: dict[str, dict] = {}
        for d in self._collection_ref().stream():
            data = d.to_dict() or {}
            ns = data.get("namespace")
            if not ns:
                continue
            ts = _coerce_dt(data.get("timestamp"))
            bucket = buckets.setdefault(
                ns, {"namespace": ns, "count": 0, "latest_at": None}
            )
            bucket["count"] += 1
            if ts is not None:
                if bucket["latest_at"] is None or ts > bucket["latest_at"]:
                    bucket["latest_at"] = ts
        return sorted(buckets.values(), key=lambda b: b["namespace"])

    def delete_expired(self, now: datetime | None = None) -> int:
        """Delete entries whose expires_at is in the past. Returns count."""
        cutoff = now or datetime.now(timezone.utc)
        to_delete: list[str] = []
        for d in self._collection_ref().stream():
            data = d.to_dict() or {}
            exp = _coerce_dt(data.get("expires_at"))
            if exp is not None and exp < cutoff:
                to_delete.append(d.id)
        for doc_id in to_delete:
            self._collection_ref().document(doc_id).delete()
        return len(to_delete)
