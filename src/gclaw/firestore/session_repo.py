"""Session CRUD operations on Firestore.

Collection path: users/{userId}/sessions/{sessionId}
"""

from __future__ import annotations

from datetime import datetime

from google.cloud.firestore import Client as FirestoreClient

from gclaw.models.session import Session, SessionStatus


class SessionRepo:
    """Synchronous Firestore repository for sessions.

    Can be created with a fixed user_id (dev mode) or with user_id passed
    per-method call (auth mode). Per-method user_id wins over the init
    default. Raises ValueError if neither is provided at call time.
    """

    def __init__(self, db: FirestoreClient, user_id: str | None = None) -> None:
        self._db = db
        self._default_user_id = user_id

    def _collection_ref(self, user_id: str | None = None):
        uid = user_id or self._default_user_id
        if uid is None:
            raise ValueError("user_id required — not set at init or in method call")
        return (
            self._db.collection("users")
            .document(uid)
            .collection("sessions")
        )

    def create(self, session: Session, user_id: str | None = None) -> Session:
        doc_ref = self._collection_ref(user_id).document(session.id)
        doc_ref.set(session.to_firestore_dict())
        return session

    def get(self, session_id: str, user_id: str | None = None) -> Session | None:
        doc = self._collection_ref(user_id).document(session_id).get()
        if not doc.exists:
            return None
        return Session.from_firestore_dict(doc.id, doc.to_dict())

    def update(self, session: Session, user_id: str | None = None) -> Session:
        doc_ref = self._collection_ref(user_id).document(session.id)
        doc_ref.set(session.to_firestore_dict())
        return session

    def delete(self, session_id: str, user_id: str | None = None) -> None:
        self._collection_ref(user_id).document(session_id).delete()

    def list_active(self, user_id: str | None = None) -> list[Session]:
        docs = (
            self._collection_ref(user_id)
            .where("status", "==", SessionStatus.ACTIVE.value)
            .stream()
        )
        return [
            Session.from_firestore_dict(doc.id, doc.to_dict()) for doc in docs
        ]

    def list_active_older_than(
        self, cutoff: datetime, user_id: str | None = None
    ) -> list[Session]:
        """Return active sessions whose `updated_at` is <= cutoff.

        Used by the heartbeat auto-end sweep to find idle sessions that
        should have their memories extracted and be marked ended. The
        `updated_at` compare is done in Python rather than via a Firestore
        composite index to avoid requiring an index deployment for what is
        currently a single-user scan.
        """
        active = self.list_active(user_id=user_id)
        return [s for s in active if s.updated_at <= cutoff]
