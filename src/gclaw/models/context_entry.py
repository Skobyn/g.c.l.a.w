"""Data model for shared-context entries.

Producer agents write curated data to named namespaces; consumer agents
read the latest entry per namespace. Small text stays inline; anything
larger (or binary) is offloaded to GCS and the Firestore doc carries
only the gs:// pointer + metadata.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, ConfigDict, Field


def _default_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=30)


class ContextEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: f"ctx_{uuid.uuid4().hex[:12]}")
    namespace: str
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    created_by: str = ""
    content: str | None = None
    blob_url: str | None = None
    blob_mime: str | None = None
    metadata: dict = Field(default_factory=dict)
    expires_at: datetime = Field(default_factory=_default_expiry)

    def to_firestore_dict(self) -> dict:
        d = self.model_dump(mode="json")
        d.pop("id", None)
        return d

    @classmethod
    def from_firestore_dict(cls, doc_id: str, data: dict) -> "ContextEntry":
        data = dict(data)
        return cls(id=doc_id, **data)
