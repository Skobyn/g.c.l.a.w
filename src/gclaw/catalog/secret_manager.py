"""SecretManagerService — thin wrapper around google-cloud-secret-manager
for the admin UI write/rotate/list flows.

All created secrets are labeled ``app=gclaw, kind=api-key`` so list
operations can filter cleanly without enumerating every secret in the
project.

SDK imports are lazy so tests / environments without the
``google-cloud-secret-manager`` package can still construct the service
(calls will raise). Permission errors from the SA are surfaced with a
hint pointing at ``roles/secretmanager.secretVersionAdder`` so the admin
UI can show an actionable banner.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_NAME_PREFIX = "watson-"
_INVALID_CHARS = re.compile(r"[^a-z0-9-]")
_MAX_NAME_LEN = 255


class SecretManagerPermissionError(RuntimeError):
    """Raised when the runtime SA lacks SM permissions."""


class SecretManagerNotFoundError(LookupError):
    """Raised when a referenced secret does not exist."""


class SecretManagerService:
    """Thin wrapper that encapsulates all SM operations used by the
    admin routes. Keeps SDK calls off the route handlers.
    """

    def __init__(self, project: str) -> None:
        if not project:
            raise ValueError("project is required")
        self._project = project
        self._client = None

    # --- Client ---------------------------------------------------------

    def _get_client(self):
        if self._client is None:
            from google.cloud import secretmanager  # type: ignore

            self._client = secretmanager.SecretManagerServiceClient()
        return self._client

    @property
    def project(self) -> str:
        return self._project

    def _parent(self) -> str:
        return f"projects/{self._project}"

    def _secret_path(self, name: str) -> str:
        return f"projects/{self._project}/secrets/{name}"

    def _latest_path(self, name: str) -> str:
        return f"{self._secret_path(name)}/versions/latest"

    # --- Name handling --------------------------------------------------

    @staticmethod
    def normalize_name(raw: str) -> str:
        """Lowercase, strip invalid chars, ensure ``watson-`` prefix."""
        if not raw:
            raise ValueError("secret name is required")
        s = raw.strip().lower()
        s = _INVALID_CHARS.sub("-", s)
        s = re.sub(r"-+", "-", s).strip("-")
        if not s:
            raise ValueError("secret name is empty after normalization")
        if not s.startswith(_NAME_PREFIX):
            s = _NAME_PREFIX + s
        if len(s) > _MAX_NAME_LEN:
            s = s[:_MAX_NAME_LEN].rstrip("-")
        if not _NAME_RE.match(s):
            raise ValueError(f"invalid secret name: {raw!r}")
        return s

    # --- Error mapping --------------------------------------------------

    @staticmethod
    def _map_exc(exc: Exception, *, op: str) -> Exception:
        msg = str(exc)
        # google.api_core.exceptions imports lazily
        try:
            from google.api_core import exceptions as gexc  # type: ignore
        except Exception:
            gexc = None  # type: ignore[assignment]

        if gexc is not None:
            if isinstance(exc, gexc.NotFound):
                return SecretManagerNotFoundError(msg)
            if isinstance(exc, (gexc.PermissionDenied, gexc.Forbidden)):
                return SecretManagerPermissionError(
                    "Secret Manager permission denied. The runtime service "
                    "account needs roles/secretmanager.admin (or at minimum "
                    "roles/secretmanager.secretVersionAdder + "
                    "roles/secretmanager.viewer). "
                    f"Underlying error during {op}: {msg}"
                )
        # Fallback string sniffing
        low = msg.lower()
        if "permission" in low and "denied" in low:
            return SecretManagerPermissionError(
                "Secret Manager permission denied. The runtime service "
                "account needs roles/secretmanager.secretVersionAdder. "
                f"Underlying error during {op}: {msg}"
            )
        if "not found" in low or "404" in low:
            return SecretManagerNotFoundError(msg)
        return exc

    # --- Ops ------------------------------------------------------------

    def _secret_exists(self, name: str) -> bool:
        client = self._get_client()
        try:
            client.get_secret(name=self._secret_path(name))
            return True
        except Exception as exc:
            mapped = self._map_exc(exc, op="get_secret")
            if isinstance(mapped, SecretManagerNotFoundError):
                return False
            if isinstance(mapped, SecretManagerPermissionError):
                raise mapped from exc
            return False

    def _create_secret(self, name: str) -> None:
        client = self._get_client()
        try:
            client.create_secret(
                request={
                    "parent": self._parent(),
                    "secret_id": name,
                    "secret": {
                        "replication": {"automatic": {}},
                        "labels": {"app": "watson", "kind": "api-key"},
                    },
                }
            )
        except Exception as exc:
            raise self._map_exc(exc, op="create_secret") from exc

    def _add_version(self, name: str, value: str) -> str:
        """Add a version and return its short version id (e.g. ``"1"``)."""
        client = self._get_client()
        try:
            resp = client.add_secret_version(
                request={
                    "parent": self._secret_path(name),
                    "payload": {"data": value.encode("utf-8")},
                }
            )
        except Exception as exc:
            raise self._map_exc(exc, op="add_secret_version") from exc
        # resp.name = projects/P/secrets/N/versions/<id>
        full = getattr(resp, "name", "") or ""
        vid = full.rsplit("/", 1)[-1] if full else ""
        return vid or "latest"

    def write(
        self,
        *,
        name: str,
        value: str,
        create_if_missing: bool = True,
    ) -> dict:
        """Ensure the secret exists, add a new version, return details."""
        if not value:
            raise ValueError("value is required")
        norm = self.normalize_name(name)
        created = False
        if not self._secret_exists(norm):
            if not create_if_missing:
                raise SecretManagerNotFoundError(
                    f"secret {norm!r} does not exist"
                )
            self._create_secret(norm)
            created = True
        version_id = self._add_version(norm, value)
        return {
            "name": norm,
            "path": self._latest_path(norm),
            "version_id": version_id,
            "created_secret": created,
        }

    def rotate(self, *, name: str, value: str) -> dict:
        """Add a new version to an EXISTING secret. 404s if missing."""
        if not value:
            raise ValueError("value is required")
        norm = self.normalize_name(name)
        if not self._secret_exists(norm):
            raise SecretManagerNotFoundError(
                f"secret {norm!r} does not exist"
            )
        version_id = self._add_version(norm, value)
        return {
            "name": norm,
            "path": self._latest_path(norm),
            "version_id": version_id,
        }

    def list_gclaw_secrets(self) -> list[dict]:
        """List secrets GClaw has visibility into.

        Union of:
          - secrets labelled ``app=watson`` (canonical) or ``app=gclaw``
            (legacy — newly created by older GClaw versions), and
          - any secret whose name starts with ``watson-`` (picks up
            secrets created outside GClaw that we share read access to).

        Names + latest-version timestamps only.
        """
        client = self._get_client()

        # Page through all secrets once; filter in memory. A single-label
        # server-side filter would miss unlabelled watson-* secrets, and
        # a label=(watson OR gclaw) filter isn't expressible in the SM
        # list filter syntax.
        try:
            it = client.list_secrets(request={"parent": self._parent()})
        except Exception as exc:
            raise self._map_exc(exc, op="list_secrets") from exc

        seen: set[str] = set()
        results: list[dict] = []
        for sec in it:
            full = getattr(sec, "name", "") or ""
            short = full.rsplit("/", 1)[-1] if full else ""
            if not short or short in seen:
                continue
            labels = dict(getattr(sec, "labels", {}) or {})
            included = (
                labels.get("app") in ("watson", "gclaw")
                or short.startswith(_NAME_PREFIX)
            )
            if not included:
                continue
            seen.add(short)
            latest_ts = self._latest_version_created_at(short)
            results.append(
                {
                    "name": short,
                    "path": self._latest_path(short),
                    "latest_version_created_at": latest_ts,
                }
            )
        return results

    def _latest_version_created_at(self, name: str) -> str | None:
        client = self._get_client()
        try:
            v = client.get_secret_version(
                name=f"{self._secret_path(name)}/versions/latest"
            )
        except Exception:
            return None
        ct = getattr(v, "create_time", None)
        if ct is None:
            return None
        # google.protobuf.Timestamp or datetime
        try:
            if hasattr(ct, "ToDatetime"):
                dt = ct.ToDatetime().replace(tzinfo=timezone.utc)
            elif isinstance(ct, datetime):
                dt = ct if ct.tzinfo else ct.replace(tzinfo=timezone.utc)
            else:
                return None
            return dt.isoformat()
        except Exception:
            return None


def _unused_keep_import(_: Any) -> None:
    """Silence unused-import linters for forward-compat."""
    return None
