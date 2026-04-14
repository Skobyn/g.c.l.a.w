"""Firestore repo for AgentOverride documents.

Collection path: ``config/agent_overrides/{agent_name}``. Doc id is the
agent name so merge-by-name is a single-key lookup.
"""

from __future__ import annotations

from datetime import datetime, timezone

from google.cloud.firestore import Client as FirestoreClient

from gclaw.models.agent_config import AgentOverride


def _overrides_doc(db: FirestoreClient):
    return db.collection("config").document("agent_overrides")


class AgentOverrideRepo:
    """CRUD for AgentOverride records. System-wide (not per-user)."""

    def __init__(self, db: FirestoreClient) -> None:
        self._db = db

    def _collection_ref(self):
        return _overrides_doc(self._db).collection("items")

    def create(self, override: AgentOverride) -> AgentOverride:
        override.updated_at = datetime.now(timezone.utc)
        doc_ref = self._collection_ref().document(override.agent_name)
        doc_ref.set(override.to_firestore_dict())
        return override

    def get(self, agent_name: str) -> AgentOverride | None:
        doc = self._collection_ref().document(agent_name).get()
        if not doc.exists:
            return None
        return AgentOverride.from_firestore_dict(doc.id, doc.to_dict() or {})

    def update(self, override: AgentOverride) -> AgentOverride:
        override.updated_at = datetime.now(timezone.utc)
        doc_ref = self._collection_ref().document(override.agent_name)
        doc_ref.set(override.to_firestore_dict())
        return override

    def delete(self, agent_name: str) -> None:
        self._collection_ref().document(agent_name).delete()

    def list_all(self) -> list[AgentOverride]:
        docs = self._collection_ref().stream()
        return [
            AgentOverride.from_firestore_dict(doc.id, doc.to_dict() or {})
            for doc in docs
        ]
