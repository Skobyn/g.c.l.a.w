"""Connection models for cross-user A2A protocol."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing_extensions import Self

from pydantic import BaseModel, Field


class ConnectionStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    REJECTED = "rejected"
    REVOKED = "revoked"


class ConnectionPermission(str, Enum):
    """Permission levels — hierarchical: full > task > write > read."""

    READ = "read"
    WRITE = "write"
    TASK = "task"
    FULL = "full"


# Permission hierarchy for comparison
_PERMISSION_RANK: dict[ConnectionPermission, int] = {
    ConnectionPermission.READ: 0,
    ConnectionPermission.WRITE: 1,
    ConnectionPermission.TASK: 2,
    ConnectionPermission.FULL: 3,
}


class Connection(BaseModel):
    """A cross-user connection record.

    Bilateral — both users have a matching record in their
    ``connections/`` subcollection.
    """

    id: str = Field(
        default_factory=lambda: f"conn_{uuid.uuid4().hex[:12]}"
    )
    from_user_id: str
    to_user_id: str
    status: ConnectionStatus = ConnectionStatus.PENDING
    permission: ConnectionPermission = ConnectionPermission.READ
    shared_channel: str = ""
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def has_permission(self, required: ConnectionPermission) -> bool:
        """Check if this connection meets the required permission level."""
        return _PERMISSION_RANK[self.permission] >= _PERMISSION_RANK[required]

    def to_firestore_dict(self) -> dict:
        d = self.model_dump(mode="json")
        d.pop("id")
        return d

    @classmethod
    def from_firestore_dict(cls, doc_id: str, data: dict) -> Self:
        return cls(id=doc_id, **data)
