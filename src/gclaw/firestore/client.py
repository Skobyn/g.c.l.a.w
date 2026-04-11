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
        import os
        # WSL2 gRPC fix — force native DNS resolver
        if "WSL" in os.uname().release:
            os.environ.setdefault("GRPC_DNS_RESOLVER", "native")
        _client = firestore.Client(project=project, database=database)
    return _client
