"""Session CRUD operations on Firestore.

Collection path: users/{userId}/sessions/{sessionId}
"""

from __future__ import annotations

from datetime import datetime

from google.cloud.firestore import Client as FirestoreClient

from gclaw.models.session import Session, SessionStatus


class SessionRepo:
    """Synchronous Firestore repository for sessions."""

    def __init__(self, db: FirestoreClient, user_id: str) -> None:
        self._db = db
        self._user_id = user_id

    def _collection_ref(self):
        return (
            self._db.collection("users")
            .document(self._user_id)
            .collection("sessions")
        )

    def create(self, session: Session) -> Session:
        doc_ref = self._collection_ref().document(session.id)
        doc_ref.set(session.to_firestore_dict())
        return session

    def get(self, session_id: str) -> Session | None:
        doc = self._collection_ref().document(session_id).get()
        if not doc.exists:
            return None
        return Session.from_firestore_dict(doc.id, doc.to_dict())

    def update(self, session: Session) -> Session:
        doc_ref = self._collection_ref().document(session.id)
        doc_ref.set(session.to_firestore_dict())
        return session

    def delete(self, session_id: str) -> None:
        self._collection_ref().document(session_id).delete()

    def list_active(self) -> list[Session]:
        docs = (
            self._collection_ref()
            .where("status", "==", SessionStatus.ACTIVE.value)
            .stream()
        )
        return [
            Session.from_firestore_dict(doc.id, doc.to_dict()) for doc in docs
        ]

    def list_active_older_than(self, cutoff: datetime) -> list[Session]:
        """Return active sessions whose `updated_at` is <= cutoff.

        Used by the heartbeat auto-end sweep to find idle sessions that
        should have their memories extracted and be marked ended. The
        `updated_at` compare is done in Python rather than via a Firestore
        composite index to avoid requiring an index deployment for what is
        currently a single-user scan.
        """
        active = self.list_active()
        return [s for s in active if s.updated_at <= cutoff]
