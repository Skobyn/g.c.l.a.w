"""Heartbeat logging model and Firestore repository.

Collection path: users/{userId}/heartbeat_logs/{logId}
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from typing_extensions import Self
from google.cloud.firestore import Client as FirestoreClient


class HeartbeatLog(BaseModel):
    """A single heartbeat cycle log entry."""

    id: str = Field(default_factory=lambda: f"hb_{uuid.uuid4().hex[:12]}")
    context_summary: str
    reasoning: str
    actions_taken: list[str] = Field(default_factory=list)
    tasks_created: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_firestore_dict(self) -> dict:
        d = self.model_dump(mode="json")
        d.pop("id")
        return d

    @classmethod
    def from_firestore_dict(cls, doc_id: str, data: dict) -> Self:
        return cls(id=doc_id, **data)


class HeartbeatLogRepo:
    """Firestore repository for heartbeat logs."""

    def __init__(self, db: FirestoreClient, user_id: str) -> None:
        self._db = db
        self._user_id = user_id

    def _collection_ref(self):
        return (
            self._db.collection("users")
            .document(self._user_id)
            .collection("heartbeat_logs")
        )

    def save(self, log: HeartbeatLog) -> HeartbeatLog:
        doc_ref = self._collection_ref().document(log.id)
        doc_ref.set(log.to_firestore_dict())
        return log

    def list_recent(self, limit: int = 10) -> list[HeartbeatLog]:
        docs = (
            self._collection_ref()
            .order_by("timestamp", direction="DESCENDING")
            .limit(limit)
            .stream()
        )
        return [
            HeartbeatLog.from_firestore_dict(doc.id, doc.to_dict())
            for doc in docs
        ]
