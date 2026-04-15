"""GCS blob helper for large shared-context payloads."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from google.cloud import storage

logger = logging.getLogger(__name__)


_MIME_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "text/markdown": ".md",
    "text/plain": ".txt",
    "text/html": ".html",
    "application/json": ".json",
    "application/pdf": ".pdf",
}


def _ext_from_mime(mime: str | None) -> str:
    if not mime:
        return ".bin"
    return _MIME_EXT.get(mime.lower(), ".bin")


class BlobStore:
    def __init__(self, project: str, bucket_name: str) -> None:
        self._project = project
        self._bucket_name = bucket_name
        self._client: storage.Client | None = None
        self._bucket_ready = False

    @property
    def bucket_name(self) -> str:
        return self._bucket_name

    def _bucket(self):
        if self._client is None:
            self._client = storage.Client(project=self._project)
        return self._client.bucket(self._bucket_name)

    def ensure_bucket(self) -> None:
        """Idempotent. Creates bucket with 30-day TTL if missing.

        Tolerates missing ``storage.admin`` permission — the caller gets
        a surfaced error on the subsequent upload rather than a crash at
        service startup.
        """
        if self._bucket_ready:
            return
        bucket = self._bucket()
        try:
            bucket.reload()
            self._bucket_ready = True
            return
        except Exception as e:
            logger.info(
                "bucket %s reload failed (%s); attempting create",
                self._bucket_name, e,
            )
        try:
            assert self._client is not None
            new_bucket = self._client.create_bucket(
                self._bucket_name, location="us-central1"
            )
            new_bucket.add_lifecycle_delete_rule(age=30)
            new_bucket.patch()
            self._bucket_ready = True
        except Exception:
            logger.warning(
                "bucket %s create failed — uploads will surface errors",
                self._bucket_name,
                exc_info=True,
            )
            # Leave _bucket_ready False; subsequent call retries.

    def upload(
        self, *, namespace: str, entry_id: str, data: bytes, mime: str
    ) -> str:
        """Returns gs:// URL."""
        self.ensure_bucket()
        date_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # Normalize namespace to a safe path segment.
        safe_ns = namespace.replace("/", "_").strip() or "default"
        ext = _ext_from_mime(mime)
        name = f"{safe_ns}/{date_prefix}/{entry_id}{ext}"
        blob = self._bucket().blob(name)
        blob.upload_from_string(data, content_type=mime)
        return f"gs://{self._bucket_name}/{name}"

    def signed_url(self, gs_url: str, *, minutes: int = 15) -> str:
        prefix = f"gs://{self._bucket_name}/"
        if not gs_url.startswith(prefix):
            raise ValueError(f"gs_url outside configured bucket: {gs_url}")
        name = gs_url[len(prefix):]
        blob = self._bucket().blob(name)
        return blob.generate_signed_url(
            expiration=timedelta(minutes=minutes), method="GET"
        )

    def delete(self, gs_url: str) -> None:
        prefix = f"gs://{self._bucket_name}/"
        if not gs_url.startswith(prefix):
            raise ValueError(f"gs_url outside configured bucket: {gs_url}")
        name = gs_url[len(prefix):]
        try:
            self._bucket().blob(name).delete()
        except Exception:
            logger.warning("blob delete failed for %s", gs_url, exc_info=True)
