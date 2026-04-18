"""GitHub Copilot short-lived token cache.

Copilot's chat/responses endpoints reject the long-lived ``ghu_`` GitHub
user token for most models (notably the codex family); they require a
short-lived session token obtained by exchanging the ``ghu_`` against
``GET https://api.github.com/copilot_internal/v2/token``.

The catalog stores the raw ``ghu_`` in Secret Manager. This module reads
it, exchanges it for a short-lived bearer (~30 min TTL), caches in
process memory keyed by SM path, and refreshes on the next call once
near expiry. Nothing is written back to SM — the exchanged token is
short-lived by design.

Never logs token values; truncation is max 12 chars + "…".
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


EXCHANGE_URL = "https://api.github.com/copilot_internal/v2/token"
HTTP_TIMEOUT_SECONDS = 15.0
# Refresh when this close to expiry (seconds). Copilot tokens live ~30
# minutes so a 2-minute margin keeps us well clear of races.
REFRESH_MARGIN_SECONDS = 120
# Default Editor-Version we report to GitHub. Copilot's IDE-auth check
# rejects calls missing this header; the exact value doesn't appear to
# be validated, but we mimic copilot-api upstream.
DEFAULT_EDITOR_VERSION = "vscode/1.95.0"
DEFAULT_INTEGRATION_ID = "vscode-chat"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _truncate_for_log(value: str | None) -> str:
    if not value:
        return "<empty>"
    return value[:12] + ("…" if len(value) > 12 else "")


class CopilotExchangeError(RuntimeError):
    """Raised when the /copilot_internal/v2/token exchange fails."""


class CopilotTokenCache:
    """Reads GitHub user tokens from Secret Manager, exchanges them for
    short-lived Copilot session tokens, and caches the result in memory.

    Thread-safe for concurrent async callers via per-path locks. The
    Secret Manager client must expose ``_get_client()`` returning a
    google-cloud-secretmanager client — matches the project's
    ``SecretManagerService`` surface.
    """

    def __init__(
        self,
        *,
        sm_service: Any,
        http_client: Any = None,
        editor_version: str = DEFAULT_EDITOR_VERSION,
        integration_id: str = DEFAULT_INTEGRATION_ID,
        timeout_seconds: float = HTTP_TIMEOUT_SECONDS,
    ) -> None:
        self._sm = sm_service
        self._http = http_client
        self._editor_version = editor_version
        self._integration_id = integration_id
        self._timeout = timeout_seconds
        # sm_path -> (access_token, expires_at_datetime)
        self._cache: dict[str, tuple[str, datetime]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock_for(self, sm_path: str) -> asyncio.Lock:
        lock = self._locks.get(sm_path)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[sm_path] = lock
        return lock

    async def _get_http(self):
        if self._http is not None:
            return self._http
        import httpx  # lazy

        self._http = httpx.AsyncClient(timeout=self._timeout)
        return self._http

    def _sm_read_sync(self, sm_path: str) -> str | None:
        try:
            client = self._sm._get_client()  # type: ignore[attr-defined]
            resp = client.access_secret_version(name=sm_path)
            return resp.payload.data.decode("utf-8").strip()
        except Exception as e:
            logger.warning(
                "copilot-cache: SM read failed for %s: %s", sm_path, e
            )
            return None

    async def _exchange(self, user_token: str) -> tuple[str, datetime]:
        http = await self._get_http()
        headers = {
            "Authorization": f"token {user_token}",
            "Accept": "application/json",
            "Editor-Version": self._editor_version,
            "Copilot-Integration-Id": self._integration_id,
        }
        try:
            resp = await http.get(EXCHANGE_URL, headers=headers)
        except Exception as e:
            raise CopilotExchangeError(
                f"HTTP error calling exchange endpoint: {e}"
            ) from e

        status = getattr(resp, "status_code", 0)
        if status < 200 or status >= 300:
            detail = ""
            try:
                detail = resp.text
            except Exception:
                pass
            raise CopilotExchangeError(
                f"exchange endpoint returned {status}: {detail[:200]}"
            )

        try:
            data = resp.json()
        except Exception as e:
            raise CopilotExchangeError(
                f"exchange endpoint returned non-JSON body: {e}"
            ) from e
        if not isinstance(data, dict):
            raise CopilotExchangeError("exchange response was not an object")

        access = data.get("token")
        if not access:
            raise CopilotExchangeError("exchange response missing 'token'")

        # expires_at is a UNIX timestamp in Copilot's response.
        expires_raw = data.get("expires_at")
        try:
            expires_ts = int(expires_raw) if expires_raw is not None else 0
        except (TypeError, ValueError):
            expires_ts = 0
        if expires_ts > 0:
            expires_at = datetime.fromtimestamp(expires_ts, tz=timezone.utc)
        else:
            # Fallback: assume 25 min (slightly under GitHub's typical 30).
            expires_at = datetime.fromtimestamp(
                time.time() + 25 * 60, tz=timezone.utc
            )
        logger.info(
            "copilot-cache: exchanged token, expires_at=%s prefix=%s",
            expires_at.isoformat(),
            _truncate_for_log(access),
        )
        return access, expires_at

    def _cached_valid(self, sm_path: str) -> str | None:
        entry = self._cache.get(sm_path)
        if entry is None:
            return None
        token, expires_at = entry
        remaining = (expires_at - _now()).total_seconds()
        if remaining <= REFRESH_MARGIN_SECONDS:
            return None
        return token

    async def get_access_token(self, sm_path: str) -> str | None:
        """Return a fresh Copilot session token for the given SM path.

        Reads the raw GitHub user token from SM, exchanges it for a
        Copilot session token, caches the result. On exchange failure
        returns None so the caller can surface a clean error.
        """
        cached = self._cached_valid(sm_path)
        if cached is not None:
            return cached

        async with self._lock_for(sm_path):
            # Re-check under lock — another caller may have filled the cache.
            cached = self._cached_valid(sm_path)
            if cached is not None:
                return cached

            user_token = await asyncio.to_thread(self._sm_read_sync, sm_path)
            if not user_token:
                return None
            try:
                token, expires_at = await self._exchange(user_token)
            except CopilotExchangeError as e:
                logger.warning(
                    "copilot-cache: exchange failed for %s: %s", sm_path, e
                )
                return None
            self._cache[sm_path] = (token, expires_at)
            return token

    def invalidate(self, sm_path: str) -> None:
        """Drop any cached token for ``sm_path`` (forcing re-exchange next
        call). Useful when the caller observes a 401 downstream.
        """
        self._cache.pop(sm_path, None)
