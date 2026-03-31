"""Connection service — cross-user A2A connection lifecycle."""

from __future__ import annotations

from datetime import datetime, timezone

from google.cloud.firestore import Client as FirestoreClient

from gclaw.firestore.connection_repo import ConnectionRepo
from gclaw.models.connection import (
    Connection,
    ConnectionPermission,
    ConnectionStatus,
)


def _make_shared_channel(user_a: str, user_b: str) -> str:
    """Deterministic shared channel name (alphabetical order)."""
    parts = sorted([user_a, user_b])
    return f"{parts[0]}__{parts[1]}"


class ConnectionService:
    """Business logic for cross-user A2A connections.

    Connections are bilateral — both users hold a matching record
    in their ``users/{userId}/connections/`` subcollection.
    """

    def __init__(self, db: FirestoreClient) -> None:
        self._db = db

    def _get_repo(self, user_id: str) -> ConnectionRepo:
        return ConnectionRepo(self._db, user_id)

    def request_connection(
        self,
        from_user_id: str,
        to_user_id: str,
        permission: ConnectionPermission = ConnectionPermission.READ,
    ) -> Connection:
        """Send a connection request from one user to another.

        Creates a PENDING record in both users' subcollections.

        Raises:
            ValueError: If connecting to self or duplicate request.
        """
        if from_user_id == to_user_id:
            raise ValueError("Cannot connect to yourself")

        # Check for existing connection
        from_repo = self._get_repo(from_user_id)
        existing = from_repo.find_by_peer(to_user_id)
        if existing is not None:
            raise ValueError(
                f"Connection already exists with status: {existing.status}"
            )

        conn = Connection(
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            status=ConnectionStatus.PENDING,
            permission=permission,
        )

        # Write to both users' subcollections (same id for correlation)
        from_repo.create(conn)
        to_repo = self._get_repo(to_user_id)
        to_repo.create(conn)

        return conn

    def accept_connection(
        self,
        user_id: str,
        connection_id: str,
    ) -> Connection:
        """Accept a pending connection request.

        Only the recipient (to_user_id) can accept.
        Sets status to ACTIVE and creates a shared channel.

        Raises:
            ValueError: If not found, not recipient, or not pending.
        """
        repo = self._get_repo(user_id)
        conn = repo.get(connection_id)
        if conn is None:
            raise ValueError(f"Connection {connection_id} not found")
        if conn.to_user_id != user_id:
            raise ValueError("Only the recipient can accept")
        if conn.status != ConnectionStatus.PENDING:
            raise ValueError(f"Cannot accept connection in status: {conn.status}")

        shared_channel = _make_shared_channel(
            conn.from_user_id, conn.to_user_id
        )
        now = datetime.now(timezone.utc)

        updated = conn.model_copy(update={
            "status": ConnectionStatus.ACTIVE,
            "shared_channel": shared_channel,
            "updated_at": now,
        })

        # Update both users' records
        repo.update(updated)
        peer_repo = self._get_repo(conn.from_user_id)
        peer_repo.update(updated)

        return updated

    def reject_connection(
        self,
        user_id: str,
        connection_id: str,
    ) -> Connection:
        """Reject a pending connection request.

        Only the recipient can reject.

        Raises:
            ValueError: If not found, not recipient, or not pending.
        """
        repo = self._get_repo(user_id)
        conn = repo.get(connection_id)
        if conn is None:
            raise ValueError(f"Connection {connection_id} not found")
        if conn.to_user_id != user_id:
            raise ValueError("Only the recipient can reject")
        if conn.status != ConnectionStatus.PENDING:
            raise ValueError(f"Cannot reject connection in status: {conn.status}")

        now = datetime.now(timezone.utc)
        updated = conn.model_copy(update={
            "status": ConnectionStatus.REJECTED,
            "updated_at": now,
        })

        repo.update(updated)
        peer_repo = self._get_repo(conn.from_user_id)
        peer_repo.update(updated)

        return updated

    def revoke_connection(
        self,
        user_id: str,
        connection_id: str,
    ) -> Connection:
        """Revoke an active connection. Either user can revoke.

        Raises:
            ValueError: If not found or not active.
        """
        repo = self._get_repo(user_id)
        conn = repo.get(connection_id)
        if conn is None:
            raise ValueError(f"Connection {connection_id} not found")
        if conn.status != ConnectionStatus.ACTIVE:
            raise ValueError(f"Cannot revoke connection in status: {conn.status}")
        if user_id not in (conn.from_user_id, conn.to_user_id):
            raise ValueError("Not a party to this connection")

        now = datetime.now(timezone.utc)
        updated = conn.model_copy(update={
            "status": ConnectionStatus.REVOKED,
            "shared_channel": "",
            "updated_at": now,
        })

        repo.update(updated)
        peer_id = (
            conn.to_user_id
            if conn.from_user_id == user_id
            else conn.from_user_id
        )
        peer_repo = self._get_repo(peer_id)
        peer_repo.update(updated)

        return updated

    def check_permission(
        self,
        user_id: str,
        connection_id: str,
        required: ConnectionPermission,
    ) -> Connection:
        """Verify a connection is active and has sufficient permission.

        Returns the connection if valid.

        Raises:
            ValueError: If connection not found or not active.
            PermissionError: If permission is insufficient.
        """
        repo = self._get_repo(user_id)
        conn = repo.get(connection_id)
        if conn is None:
            raise ValueError(f"Connection {connection_id} not found")
        if conn.status != ConnectionStatus.ACTIVE:
            raise ValueError("Connection is not active")
        if not conn.has_permission(required):
            raise PermissionError(
                f"Connection permission '{conn.permission.value}' "
                f"is insufficient — requires '{required.value}'"
            )
        return conn

    def list_connections(
        self,
        user_id: str,
        status: ConnectionStatus | None = None,
    ) -> list[Connection]:
        """List connections for a user, optionally filtered by status."""
        repo = self._get_repo(user_id)
        if status is not None:
            return repo.list_by_status(status)
        return repo.list_active()

    def list_pending_incoming(self, user_id: str) -> list[Connection]:
        """List pending incoming connection requests."""
        repo = self._get_repo(user_id)
        return repo.list_pending_incoming()
