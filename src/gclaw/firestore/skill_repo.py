"""Skill registry CRUD operations on Firestore.

Collection path: users/{userId}/skills/{skillName}
"""

from __future__ import annotations

from google.cloud.firestore import Client as FirestoreClient

from gclaw.models.skill import Skill


class SkillRepo:
    """Synchronous Firestore repository for skill definitions."""

    def __init__(self, db: FirestoreClient, user_id: str) -> None:
        self._db = db
        self._user_id = user_id

    def _collection_ref(self):
        return (
            self._db.collection("users")
            .document(self._user_id)
            .collection("skills")
        )

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
