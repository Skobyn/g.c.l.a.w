"""Board task CRUD operations on Firestore.

Collection path: users/{userId}/board/{taskId}
"""

from __future__ import annotations

from google.cloud.firestore import Client as FirestoreClient

from gclaw.models.task import BoardTask, TaskStatus


class BoardRepo:
    """Synchronous Firestore repository for board tasks."""

    def __init__(self, db: FirestoreClient, user_id: str) -> None:
        self._db = db
        self._user_id = user_id

    def _collection_ref(self):
        return (
            self._db.collection("users")
            .document(self._user_id)
            .collection("board")
        )

    def create(self, task: BoardTask) -> BoardTask:
        doc_ref = self._collection_ref().document(task.id)
        doc_ref.set(task.to_firestore_dict())
        return task

    def get(self, task_id: str) -> BoardTask | None:
        doc = self._collection_ref().document(task_id).get()
        if not doc.exists:
            return None
        return BoardTask.from_firestore_dict(doc.id, doc.to_dict())

    def update(self, task: BoardTask) -> BoardTask:
        doc_ref = self._collection_ref().document(task.id)
        doc_ref.set(task.to_firestore_dict())
        return task

    def delete(self, task_id: str) -> None:
        self._collection_ref().document(task_id).delete()

    def list_by_status(self, status: TaskStatus) -> list[BoardTask]:
        docs = (
            self._collection_ref()
            .where("status", "==", status.value)
            .stream()
        )
        return [
            BoardTask.from_firestore_dict(doc.id, doc.to_dict()) for doc in docs
        ]

    def list_by_assignee(
        self, assignee: str, status: TaskStatus | None = None
    ) -> list[BoardTask]:
        query = self._collection_ref().where("assignee", "==", assignee)
        status_value = status.value if status else [s.value for s in TaskStatus]
        query = query.where(
            "status", "==" if status else "in", status_value
        )
        docs = query.stream()
        return [
            BoardTask.from_firestore_dict(doc.id, doc.to_dict()) for doc in docs
        ]

    def list_all(self) -> list[BoardTask]:
        docs = self._collection_ref().stream()
        return [
            BoardTask.from_firestore_dict(doc.id, doc.to_dict()) for doc in docs
        ]
