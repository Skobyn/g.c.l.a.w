"""Firestore repo for the Tool Catalog.

Mirrors the shape of ``firestore/catalog_repo.py``. Collection layout:
    config/tools/{id}
"""

from __future__ import annotations

from google.cloud.firestore import Client as FirestoreClient

from gclaw.tools.catalog.models import ToolRecord


def _tools_collection(db: FirestoreClient):
    return db.collection("config").document("tools_catalog").collection("tools")


class ToolRepo:
    """CRUD for ToolRecord entries."""

    def __init__(self, db: FirestoreClient) -> None:
        self._db = db

    def _collection_ref(self):
        return _tools_collection(self._db)

    def create(self, tool: ToolRecord) -> ToolRecord:
        self._collection_ref().document(tool.id).set(tool.to_firestore_dict())
        return tool

    def get(self, tool_id: str) -> ToolRecord | None:
        doc = self._collection_ref().document(tool_id).get()
        if not doc.exists:
            return None
        return ToolRecord.from_firestore_dict(doc.id, doc.to_dict())

    def update(self, tool: ToolRecord) -> ToolRecord:
        self._collection_ref().document(tool.id).set(tool.to_firestore_dict())
        return tool

    def delete(self, tool_id: str) -> None:
        self._collection_ref().document(tool_id).delete()

    def list_all(self) -> list[ToolRecord]:
        return [
            ToolRecord.from_firestore_dict(doc.id, doc.to_dict())
            for doc in self._collection_ref().stream()
        ]
