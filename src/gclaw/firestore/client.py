"""Firestore client singleton."""

from __future__ import annotations

from google.cloud import firestore

_client: firestore.Client | None = None


def get_firestore_client(
    project: str | None = None,
    database: str = "(default)",
) -> firestore.Client:
    global _client
    if _client is None:
        _client = firestore.Client(project=project, database=database)
    return _client
