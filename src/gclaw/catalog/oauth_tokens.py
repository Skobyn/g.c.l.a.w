"""OAuth token bundles + Anthropic Claude Code refresh support.

Users paste Claude Code OAuth tokens (both access_token AND refresh_token)
through the admin UI. We bundle them into a JSON blob, store in Secret
Manager, and periodically refresh the access_token before expiry using
Anthropic's token endpoint.

Legacy compatibility: SM values that were stored as a plain access_token
string (before this module existed) parse into a bundle with only
``access_token`` set — refresh will be skipped for such bundles.

Never logs token values. Debug truncation is max 12 chars + "…".
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


# --- Defaults ---------------------------------------------------------------

# NOTE: these defaults are documented in the task but not verified against
# Anthropic's live service. Users can override via settings
# (ANTHROPIC_OAUTH_TOKEN_URL, ANTHROPIC_OAUTH_CLIENT_ID) without a redeploy.
DEFAULT_TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
DEFAULT_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
DEFAULT_EXPIRES_IN_SECONDS = 8 * 3600  # 8h
REFRESH_MARGIN_SECONDS = 600  # 10 min
HTTP_TIMEOUT_SECONDS = 15.0
CACHE_TTL_SECONDS = 60


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _truncate_for_log(value: str | None) -> str:
    if not value:
        return "<empty>"
    return value[:12] + ("…" if len(value) > 12 else "")


# --- Bundle model -----------------------------------------------------------


class OAuthTokenBundle(BaseModel):
    """JSON-serializable OAuth token bundle stored as the secret payload."""

    model_config = ConfigDict(extra="ignore")

    access_token: str
    refresh_token: str = ""
    expires_at: datetime
    token_type: str = "Bearer"
    # Opaque extra fields from the OAuth response (scopes, id_token, etc.) —
    # preserved round-trip so a refresh doesn't strip fields we don't know about.
    extra: dict[str, Any] = Field(default_factory=dict)

    def is_near_expiry(self, margin_seconds: int = REFRESH_MARGIN_SECONDS) -> bool:
        """True if within ``margin_seconds`` of expiry (or already expired)."""
        remaining = (self.expires_at - _now()).total_seconds()
        return remaining <= margin_seconds

    def has_refresh_token(self) -> bool:
        return bool(self.refresh_token)

    def to_json(self) -> str:
        # Pydantic handles datetime ISO-8601 serialization via mode="json".
        return json.dumps(self.model_dump(mode="json"))

    @classmethod
    def parse(cls, value: str | None) -> "OAuthTokenBundle | None":
        """Parse a raw SM secret value.

        Handles:
          - JSON blob with {access_token, refresh_token, expires_at, ...}
          - Plain string (legacy) — treated as access_token only, no refresh,
            expires_at far in the past so is_near_expiry=True (but refresh
            is skipped because has_refresh_token()=False).
          - None / empty — returns None.
        """
        if not value:
            return None
        stripped = value.strip()
        if not stripped:
            return None

        # JSON path
        if stripped.startswith("{"):
            try:
                data = json.loads(stripped)
            except json.JSONDecodeError:
                logger.warning(
                    "oauth-bundle: value looks like JSON but failed to parse"
                )
                return None
            if not isinstance(data, dict):
                return None
            # Accept expires_in (seconds-from-now) as an alt to expires_at,
            # because Anthropic's token endpoint returns expires_in.
            if "expires_at" not in data and "expires_in" in data:
                try:
                    expires_in = int(data["expires_in"])
                except (TypeError, ValueError):
                    expires_in = DEFAULT_EXPIRES_IN_SECONDS
                data["expires_at"] = (
                    _now() + timedelta(seconds=expires_in)
                ).isoformat()
            if "expires_at" not in data:
                data["expires_at"] = (
                    _now() + timedelta(seconds=DEFAULT_EXPIRES_IN_SECONDS)
                ).isoformat()
            # Collect unknown fields into `extra` so we don't lose them.
            known = {
                "access_token",
                "refresh_token",
                "expires_at",
                "token_type",
                "extra",
            }
            extra = dict(data.get("extra") or {})
            for k, v in data.items():
                if k not in known:
                    extra[k] = v
            data["extra"] = extra
            try:
                return cls(**{k: v for k, v in data.items() if k in known})
            except Exception:
                logger.warning(
                    "oauth-bundle: JSON shape didn't match expected schema",
                    exc_info=True,
                )
                return None

        # Plain-string fallback (legacy): treat as access_token only.
        return cls(
            access_token=stripped,
            refresh_token="",
            # Set far in the past so consumers know it could be expired,
            # but refresh is skipped (has_refresh_token=False).
            expires_at=datetime(1970, 1, 1, tzinfo=timezone.utc),
        )


# --- Refresher --------------------------------------------------------------


class OAuthRefreshError(RuntimeError):
    """Raised when Anthropic rejects a refresh token or the HTTP call fails."""


class AnthropicOAuthRefresher:
    """Swaps a refresh_token for a fresh access_token via Anthropic's token
    endpoint.

    Stateless — safe to share across tasks. The httpx client is created
    lazily on first use.
    """

    def __init__(
        self,
        *,
        token_url: str = DEFAULT_TOKEN_URL,
        client_id: str = DEFAULT_CLIENT_ID,
        http_client: Any = None,
        timeout_seconds: float = HTTP_TIMEOUT_SECONDS,
    ) -> None:
        self._token_url = token_url
        self._client_id = client_id
        self._http = http_client
        self._timeout = timeout_seconds

    async def _get_http(self):
        if self._http is not None:
            return self._http
        import httpx  # lazy

        self._http = httpx.AsyncClient(timeout=self._timeout)
        return self._http

    async def refresh(self, bundle: OAuthTokenBundle) -> OAuthTokenBundle:
        """Exchange the bundle's refresh_token for a new access_token.

        Returns a fresh bundle. Raises OAuthRefreshError on failure.
        """
        if not bundle.has_refresh_token():
            raise OAuthRefreshError(
                "cannot refresh: bundle has no refresh_token"
            )

        body = {
            "grant_type": "refresh_token",
            "refresh_token": bundle.refresh_token,
            "client_id": self._client_id,
        }
        http = await self._get_http()
        try:
            resp = await http.post(
                self._token_url,
                json=body,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
        except Exception as e:
            raise OAuthRefreshError(f"HTTP error calling token endpoint: {e}") from e

        status = getattr(resp, "status_code", 0)
        if status < 200 or status >= 300:
            # Pull as much detail as possible without logging tokens.
            detail = ""
            try:
                detail = resp.text  # type: ignore[assignment]
            except Exception:
                pass
            raise OAuthRefreshError(
                f"token endpoint returned {status}: {detail[:200]}"
            )

        try:
            data = resp.json()
        except Exception as e:
            raise OAuthRefreshError(
                f"token endpoint returned non-JSON body: {e}"
            ) from e
        if not isinstance(data, dict):
            raise OAuthRefreshError("token endpoint body was not an object")

        new_access = data.get("access_token")
        if not new_access:
            raise OAuthRefreshError("token endpoint response missing access_token")

        # Prefer a rotated refresh_token; fall back to the prior one.
        new_refresh = data.get("refresh_token") or bundle.refresh_token

        # Compute expiry
        expires_in = data.get("expires_in")
        try:
            expires_in_int = int(expires_in) if expires_in is not None else DEFAULT_EXPIRES_IN_SECONDS
        except (TypeError, ValueError):
            expires_in_int = DEFAULT_EXPIRES_IN_SECONDS
        new_expires_at = _now() + timedelta(seconds=expires_in_int)

        # Preserve prior extras, overlay any new unknown fields.
        extra = dict(bundle.extra)
        for k, v in data.items():
            if k not in ("access_token", "refresh_token", "expires_in", "token_type"):
                extra[k] = v

        token_type = data.get("token_type") or bundle.token_type or "Bearer"

        new_bundle = OAuthTokenBundle(
            access_token=new_access,
            refresh_token=new_refresh,
            expires_at=new_expires_at,
            token_type=token_type,
            extra=extra,
        )
        logger.info(
            "oauth-refresh: refreshed token, new_expiry=%s token_prefix=%s",
            new_bundle.expires_at.isoformat(),
            _truncate_for_log(new_bundle.access_token),
        )
        return new_bundle


# --- Manager ----------------------------------------------------------------


class OAuthTokenManager:
    """Reads/writes OAuth bundles to Secret Manager, with periodic refresh.

    The set of SM paths to track is populated at startup via ``register``.
    The background loop (OAuthRefreshLoop) calls ``ensure_fresh`` on each
    tracked path; runtime consumers use ``get_access_token``.

    A per-path asyncio.Lock prevents thundering-herd refreshes when many
    callers hit get_access_token at once on a near-expiry token.
    """

    def __init__(
        self,
        *,
        sm_service: Any,
        refresher: AnthropicOAuthRefresher,
        cache_ttl_seconds: float = CACHE_TTL_SECONDS,
    ) -> None:
        self._sm = sm_service
        self._refresher = refresher
        self._tracked: set[str] = set()
        # path -> (bundle, fetched_at monotonic seconds)
        self._cache: dict[str, tuple[OAuthTokenBundle, float]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._cache_ttl = cache_ttl_seconds

    # --- path tracking

    async def register(self, sm_path: str) -> None:
        if sm_path:
            self._tracked.add(sm_path)

    def tracked_paths(self) -> list[str]:
        return sorted(self._tracked)

    def _lock_for(self, sm_path: str) -> asyncio.Lock:
        lock = self._locks.get(sm_path)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[sm_path] = lock
        return lock

    # --- SM IO (sync google SDK, so run in a thread)

    def _sm_read_sync(self, sm_path: str) -> str | None:
        """Read the raw string from SM. Returns None on error."""
        try:
            # Prefer using the sm_service's client (reuses one instance).
            client = self._sm._get_client()  # type: ignore[attr-defined]
            resp = client.access_secret_version(name=sm_path)
            return resp.payload.data.decode("utf-8")
        except Exception as e:
            logger.warning(
                "oauth-manager: SM read failed for %s: %s", sm_path, e
            )
            return None

    def _sm_write_sync(self, sm_path: str, value: str) -> None:
        """Write a new version at the SM secret referenced by sm_path.

        ``sm_path`` is a full ``projects/P/secrets/N/versions/V`` path — we
        need to derive the bare secret name.
        """
        name = _secret_name_from_path(sm_path)
        if not name:
            raise ValueError(f"cannot derive secret name from path: {sm_path}")
        # rotate() rejects missing secrets; we use the lower-level write so
        # that newly-created bundles still work.
        self._sm.write(name=name, value=value, create_if_missing=True)

    async def read_bundle(self, sm_path: str) -> OAuthTokenBundle | None:
        """Read the bundle from SM (with short cache). None if unavailable."""
        cached = self._cache.get(sm_path)
        now_mono = time.monotonic()
        if cached is not None:
            bundle, fetched_at = cached
            if now_mono - fetched_at < self._cache_ttl:
                return bundle
        raw = await asyncio.to_thread(self._sm_read_sync, sm_path)
        bundle = OAuthTokenBundle.parse(raw)
        if bundle is not None:
            self._cache[sm_path] = (bundle, now_mono)
        return bundle

    async def _write_bundle(self, sm_path: str, bundle: OAuthTokenBundle) -> None:
        await asyncio.to_thread(self._sm_write_sync, sm_path, bundle.to_json())
        # Invalidate + prime cache.
        self._cache[sm_path] = (bundle, time.monotonic())

    # --- public operations

    async def get_access_token(self, sm_path: str) -> str | None:
        """Read bundle, refresh if near expiry, return current access_token.

        On refresh failure we return the (possibly stale) access_token —
        better to try a stale token than to crash the caller. The next
        API call will surface the 401 to the user via the Test button.
        """
        async with self._lock_for(sm_path):
            bundle = await self.read_bundle(sm_path)
            if bundle is None:
                return None
            if bundle.has_refresh_token() and bundle.is_near_expiry():
                try:
                    new_bundle = await self._refresher.refresh(bundle)
                    await self._write_bundle(sm_path, new_bundle)
                    return new_bundle.access_token
                except OAuthRefreshError as e:
                    logger.warning(
                        "oauth-manager: refresh failed for %s, returning stale "
                        "token (token_prefix=%s): %s",
                        sm_path,
                        _truncate_for_log(bundle.access_token),
                        e,
                    )
            return bundle.access_token

    async def ensure_fresh(self, sm_path: str) -> None:
        """Proactively refresh if near expiry. No-op otherwise."""
        async with self._lock_for(sm_path):
            bundle = await self.read_bundle(sm_path)
            if bundle is None:
                return
            if not bundle.has_refresh_token():
                return
            if not bundle.is_near_expiry():
                return
            try:
                new_bundle = await self._refresher.refresh(bundle)
                await self._write_bundle(sm_path, new_bundle)
            except OAuthRefreshError as e:
                logger.warning(
                    "oauth-manager: ensure_fresh refresh failed for %s: %s",
                    sm_path,
                    e,
                )

    async def refresh_now(self, sm_path: str) -> OAuthTokenBundle | None:
        """Force a refresh regardless of expiry (for manual admin triggers).

        Returns the new bundle on success, None if no bundle exists or
        there's no refresh_token. Raises OAuthRefreshError on failure.
        """
        async with self._lock_for(sm_path):
            bundle = await self.read_bundle(sm_path)
            if bundle is None or not bundle.has_refresh_token():
                return None
            new_bundle = await self._refresher.refresh(bundle)
            await self._write_bundle(sm_path, new_bundle)
            return new_bundle


def _secret_name_from_path(sm_path: str) -> str | None:
    """Extract the bare secret name from a SM resource path."""
    # projects/P/secrets/NAME/versions/V
    if not sm_path:
        return None
    parts = sm_path.split("/")
    try:
        i = parts.index("secrets")
    except ValueError:
        return None
    if i + 1 >= len(parts):
        return None
    return parts[i + 1]
