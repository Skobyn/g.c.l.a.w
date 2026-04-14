"""Firestore repos for the model catalog.

Catalog is system-wide (not per-user). Collections:
  config/catalog/providers/{id}
  config/catalog/models/{id}
"""

from __future__ import annotations

from google.cloud.firestore import Client as FirestoreClient

from gclaw.models.catalog import ModelProvider, ModelRecord


def _catalog_doc(db: FirestoreClient):
    return db.collection("config").document("catalog")


class ProviderRepo:
    """CRUD for ModelProvider records."""

    def __init__(self, db: FirestoreClient) -> None:
        self._db = db

    def _collection_ref(self):
        return _catalog_doc(self._db).collection("providers")

    def create(self, provider: ModelProvider) -> ModelProvider:
        doc_ref = self._collection_ref().document(provider.id)
        doc_ref.set(provider.to_firestore_dict())
        return provider

    def get(self, provider_id: str) -> ModelProvider | None:
        doc = self._collection_ref().document(provider_id).get()
        if not doc.exists:
            return None
        return ModelProvider.from_firestore_dict(doc.id, doc.to_dict())

    def update(self, provider: ModelProvider) -> ModelProvider:
        doc_ref = self._collection_ref().document(provider.id)
        doc_ref.set(provider.to_firestore_dict())
        return provider

    def delete(self, provider_id: str) -> None:
        self._collection_ref().document(provider_id).delete()

    def list_all(self) -> list[ModelProvider]:
        docs = self._collection_ref().stream()
        return [
            ModelProvider.from_firestore_dict(doc.id, doc.to_dict())
            for doc in docs
        ]


class ModelRepo:
    """CRUD for ModelRecord entries."""

    def __init__(self, db: FirestoreClient) -> None:
        self._db = db

    def _collection_ref(self):
        return _catalog_doc(self._db).collection("models")

    def create(self, model: ModelRecord) -> ModelRecord:
        doc_ref = self._collection_ref().document(model.id)
        doc_ref.set(model.to_firestore_dict())
        return model

    def get(self, model_id: str) -> ModelRecord | None:
        doc = self._collection_ref().document(model_id).get()
        if not doc.exists:
            return None
        return ModelRecord.from_firestore_dict(doc.id, doc.to_dict())

    def update(self, model: ModelRecord) -> ModelRecord:
        doc_ref = self._collection_ref().document(model.id)
        doc_ref.set(model.to_firestore_dict())
        return model

    def delete(self, model_id: str) -> None:
        self._collection_ref().document(model_id).delete()

    def list_all(self) -> list[ModelRecord]:
        docs = self._collection_ref().stream()
        return [
            ModelRecord.from_firestore_dict(doc.id, doc.to_dict())
            for doc in docs
        ]

    def list_by_provider(self, provider_id: str) -> list[ModelRecord]:
        docs = (
            self._collection_ref()
            .where("provider_id", "==", provider_id)
            .stream()
        )
        return [
            ModelRecord.from_firestore_dict(doc.id, doc.to_dict())
            for doc in docs
        ]
