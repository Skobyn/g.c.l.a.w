"""Firestore repo for the Skill registry.

Mirrors the shape of ``firestore/tool_repo.py``. Collection layout:
    config/skills_catalog/skills/{skill_name}

Skills are a shared catalog (like tools) rather than per-user data —
that keeps the registry consistent with how the factory, agent
overrides, and UI reason about skills. A future multi-tenant build
can extend this with an optional ``owner_user_id`` field rather than
swapping collection layout.
"""

from __future__ import annotations

from google.cloud.firestore import Client as FirestoreClient

from gclaw.models.skill import Skill


def _skills_collection(db: FirestoreClient):
    return (
        db.collection("config").document("skills_catalog").collection("skills")
    )


class SkillRepo:
    """Synchronous Firestore repository for skill definitions."""

    def __init__(self, db: FirestoreClient) -> None:
        self._db = db

    def _collection_ref(self):
        return _skills_collection(self._db)

    def save(self, skill: Skill) -> Skill:
        """Save or overwrite a skill definition."""
        doc_ref = self._collection_ref().document(skill.name)
        doc_ref.set(skill.to_firestore_dict())
        return skill

    def get(self, skill_name: str) -> Skill | None:
        doc = self._collection_ref().document(skill_name).get()
        if not doc.exists:
            return None
        return Skill.from_firestore_dict(doc.to_dict())

    def delete(self, skill_name: str) -> None:
        self._collection_ref().document(skill_name).delete()

    def list_all(self) -> list[Skill]:
        docs = self._collection_ref().stream()
        return [Skill.from_firestore_dict(doc.to_dict()) for doc in docs]
