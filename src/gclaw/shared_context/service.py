"""SharedContextService — orchestrates inline-vs-blob storage."""

from __future__ import annotations

import logging
from datetime import datetime

from gclaw.firestore.context_entry_repo import ContextEntryRepo
from gclaw.models.context_entry import ContextEntry
from gclaw.shared_context.blob_store import BlobStore

logger = logging.getLogger(__name__)

INLINE_MAX_BYTES = 500_000


class SharedContextService:
    def __init__(
        self,
        repo: ContextEntryRepo,
        blob_store: BlobStore | None,
    ) -> None:
        self._repo = repo
        self._blob = blob_store

    @property
    def has_blob_store(self) -> bool:
        return self._blob is not None

    def write_text(
        self,
        *,
        namespace: str,
        content: str,
        created_by: str,
        metadata: dict | None = None,
        mime: str = "text/markdown",
    ) -> ContextEntry:
        entry = ContextEntry(
            namespace=namespace,
            created_by=created_by,
            metadata=metadata or {},
            blob_mime=mime,
        )
        encoded = content.encode("utf-8")
        if len(encoded) <= INLINE_MAX_BYTES or self._blob is None:
            entry.content = content
        else:
            entry.blob_url = self._blob.upload(
                namespace=namespace,
                entry_id=entry.id,
                data=encoded,
                mime=mime,
            )
        return self._repo.create(entry)

    def write_image(
        self,
        *,
        namespace: str,
        data: bytes,
        mime: str,
        created_by: str,
        metadata: dict | None = None,
    ) -> ContextEntry:
        if self._blob is None:
            raise RuntimeError(
                "Image write requires GCS — blob_store not configured"
            )
        entry = ContextEntry(
            namespace=namespace,
            created_by=created_by,
            metadata=metadata or {},
            blob_mime=mime,
        )
        entry.blob_url = self._blob.upload(
            namespace=namespace,
            entry_id=entry.id,
            data=data,
            mime=mime,
        )
        return self._repo.create(entry)

    def read_latest(self, namespace: str) -> ContextEntry | None:
        return self._repo.latest_in(namespace)

    def list(
        self,
        namespace: str,
        limit: int = 20,
        since: datetime | None = None,
    ) -> list[ContextEntry]:
        return self._repo.list_by_namespace(
            namespace, limit=limit, since=since
        )

    def get(self, entry_id: str) -> ContextEntry | None:
        return self._repo.get(entry_id)

    def list_namespaces(self) -> list[dict]:
        return self._repo.list_namespaces()

    def delete(self, entry_id: str) -> None:
        entry = self._repo.get(entry_id)
        if entry is None:
            return
        if entry.blob_url and self._blob is not None:
            try:
                self._blob.delete(entry.blob_url)
            except Exception:
                logger.warning(
                    "blob delete failed for %s", entry.blob_url,
                    exc_info=True,
                )
        self._repo.delete(entry_id)

    def signed_url_for(
        self, entry: ContextEntry, *, minutes: int = 15
    ) -> str | None:
        if not entry.blob_url or self._blob is None:
            return None
        return self._blob.signed_url(entry.blob_url, minutes=minutes)
