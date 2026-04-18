"""System-wide runtime config stored in Firestore at ``config/system``.

Lives as a single document so we don't pay one RTT per setting and so
the schema can evolve without migrations. Today it holds just the
user timezone; future entries (default model, default notification
channel, etc.) slot in as sibling fields.

Kept intentionally thin — no caching layer, no write-through
invalidation. Admin writes are infrequent; the boot read happens once.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


_DOC_PATH = ("config", "system")


class SystemConfigRepo:
    def __init__(self, db: Any) -> None:
        self._db = db

    def _ref(self):
        col, doc = _DOC_PATH
        return self._db.collection(col).document(doc)

    def get(self) -> dict:
        """Return the config doc as a plain dict (empty if missing)."""
        try:
            snap = self._ref().get()
        except Exception:
            logger.warning("system-config: read failed", exc_info=True)
            return {}
        if not snap.exists:
            return {}
        return snap.to_dict() or {}

    def set_field(self, field: str, value: Any) -> None:
        """Write a single field into the system config doc, upserting."""
        self._ref().set({field: value}, merge=True)
