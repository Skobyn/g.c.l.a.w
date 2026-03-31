"""Connection CRUD operations on Firestore.

Collection path: users/{userId}/connections/{connectionId}
"""

from __future__ import annotations

from google.cloud.firestore import Client as FirestoreClient

from gclaw.models.connection import Connection, ConnectionStatus


class ConnectionRepo:
    """Synchronous Firestore repository for user connections."""

    def __init__(self, db: FirestoreClient, user_id: str) -> None:
        self._db = db
        self._user_id = user_id

    def _collection_ref(self):
        return (
            self._db.collection("users")
            .document(self._user_id)
            .collection("connections")
        )

    def create(self, connection: Connection) -> Connection:
        doc_ref = self._collection_ref().document(connection.id)
        doc_ref.set(connection.to_firestore_dict())
        return connection

    def get(self, connection_id: str) -> Connection | None:
        doc = self._collection_ref().document(connection_id).get()
        if not doc.exists:
            return None
        return Connection.from_firestore_dict(doc.id, doc.to_dict())

    def update(self, connection: Connection) -> Connection:
        doc_ref = self._collection_ref().document(connection.id)
        doc_ref.set(connection.to_firestore_dict())
        return connection

    def delete(self, connection_id: str) -> None:
        self._collection_ref().document(connection_id).delete()

    def list_by_status(self, status: ConnectionStatus) -> list[Connection]:
        docs = (
            self._collection_ref()
            .where("status", "==", status.value)
            .stream()
        )
        return [
            Connection.from_firestore_dict(doc.id, doc.to_dict())
            for doc in docs
        ]

    def list_active(self) -> list[Connection]:
        return self.list_by_status(ConnectionStatus.ACTIVE)

    def list_pending_incoming(self) -> list[Connection]:
        """List pending requests where this user is the recipient."""
        docs = (
            self._collection_ref()
            .where("status", "==", ConnectionStatus.PENDING.value)
            .where("to_user_id", "==", self._user_id)
            .stream()
        )
        return [
            Connection.from_firestore_dict(doc.id, doc.to_dict())
            for doc in docs
        ]

    def find_by_peer(self, peer_user_id: str) -> Connection | None:
        """Find an active or pending connection with a specific user."""
        docs = list(
            self._collection_ref()
            .where("status", "in", [
                ConnectionStatus.PENDING.value,
                ConnectionStatus.ACTIVE.value,
            ])
            .stream()
        )
        for doc in docs:
            data = doc.to_dict()
            other = (
                data.get("to_user_id")
                if data.get("from_user_id") == self._user_id
                else data.get("from_user_id")
            )
            if other == peer_user_id:
                return Connection.from_firestore_dict(doc.id, data)
        return None
