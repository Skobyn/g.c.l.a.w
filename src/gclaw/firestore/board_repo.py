"""Board task CRUD operations on Firestore.

Collection path: users/{userId}/board/{taskId}
"""

from __future__ import annotations

from google.cloud.firestore import Client as FirestoreClient

from gclaw.models.task import BoardTask, TaskStatus


class BoardRepo:
    """Synchronous Firestore repository for board tasks.

    Can be created with a fixed user_id (dev mode) or with
    user_id passed per-method call (auth mode).
    """

    def __init__(self, db: FirestoreClient, user_id: str | None = None) -> None:
        self._db = db
        self._default_user_id = user_id

    def _collection_ref(self, user_id: str | None = None):
        uid = user_id or self._default_user_id
        if uid is None:
            raise ValueError("user_id required — not set at init or in method call")
        return (
            self._db.collection("users")
            .document(uid)
            .collection("board")
        )

    def create(self, task: BoardTask, user_id: str | None = None) -> BoardTask:
        doc_ref = self._collection_ref(user_id).document(task.id)
        doc_ref.set(task.to_firestore_dict())
        return task

    def get(self, task_id: str, user_id: str | None = None) -> BoardTask | None:
        doc = self._collection_ref(user_id).document(task_id).get()
        if not doc.exists:
            return None
        return BoardTask.from_firestore_dict(doc.id, doc.to_dict())

    def update(self, task: BoardTask, user_id: str | None = None) -> BoardTask:
        doc_ref = self._collection_ref(user_id).document(task.id)
        doc_ref.set(task.to_firestore_dict())
        return task

    def delete(self, task_id: str, user_id: str | None = None) -> None:
        self._collection_ref(user_id).document(task_id).delete()

    def list_by_status(self, status: TaskStatus, user_id: str | None = None) -> list[BoardTask]:
        docs = (
            self._collection_ref(user_id)
            .where("status", "==", status.value)
            .stream()
        )
        return [
            BoardTask.from_firestore_dict(doc.id, doc.to_dict()) for doc in docs
        ]

    def list_by_assignee(
        self, assignee: str, status: TaskStatus | None = None, user_id: str | None = None
    ) -> list[BoardTask]:
        query = self._collection_ref(user_id).where("assignee", "==", assignee)
        status_value = status.value if status else [s.value for s in TaskStatus]
        query = query.where(
            "status", "==" if status else "in", status_value
        )
        docs = query.stream()
        return [
            BoardTask.from_firestore_dict(doc.id, doc.to_dict()) for doc in docs
        ]

    def list_all(self, user_id: str | None = None) -> list[BoardTask]:
        docs = self._collection_ref(user_id).stream()
        return [
            BoardTask.from_firestore_dict(doc.id, doc.to_dict()) for doc in docs
        ]
