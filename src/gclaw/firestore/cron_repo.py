"""Cron CRUD operations on Firestore.

Collection path: users/{userId}/crons/{cronId}
"""

from __future__ import annotations

from google.cloud.firestore import Client as FirestoreClient

from gclaw.models.cron import Cron, CronStatus


class CronRepo:
    """Synchronous Firestore repository for cron definitions."""

    def __init__(self, db: FirestoreClient, user_id: str) -> None:
        self._db = db
        self._user_id = user_id

    def _collection_ref(self):
        return (
            self._db.collection("users")
            .document(self._user_id)
            .collection("crons")
        )

    def create(self, cron: Cron) -> Cron:
        doc_ref = self._collection_ref().document(cron.id)
        doc_ref.set(cron.to_firestore_dict())
        return cron

    def get(self, cron_id: str) -> Cron | None:
        doc = self._collection_ref().document(cron_id).get()
        if not doc.exists:
            return None
        return Cron.from_firestore_dict(doc.id, doc.to_dict())

    def update(self, cron: Cron) -> Cron:
        doc_ref = self._collection_ref().document(cron.id)
        doc_ref.set(cron.to_firestore_dict())
        return cron

    def delete(self, cron_id: str) -> None:
        self._collection_ref().document(cron_id).delete()

    def list_all(self) -> list[Cron]:
        docs = self._collection_ref().stream()
        return [
            Cron.from_firestore_dict(doc.id, doc.to_dict()) for doc in docs
        ]

    def list_active(self) -> list[Cron]:
        docs = (
            self._collection_ref()
            .where("status", "==", CronStatus.ACTIVE.value)
            .stream()
        )
        return [
            Cron.from_firestore_dict(doc.id, doc.to_dict()) for doc in docs
        ]
