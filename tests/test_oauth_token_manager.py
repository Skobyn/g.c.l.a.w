"""Tests for OAuthTokenManager."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from gclaw.catalog.oauth_tokens import (
    AnthropicOAuthRefresher,
    OAuthRefreshError,
    OAuthTokenBundle,
    OAuthTokenManager,
)


class FakeSM:
    """Minimal fake of SecretManagerService for OAuthTokenManager."""

    def __init__(self):
        # path -> raw value
        self.store: dict[str, str] = {}
        self.writes: list[tuple[str, str]] = []

    class _Payload:
        def __init__(self, data: bytes):
            self.data = data

    class _Resp:
        def __init__(self, data: bytes):
            self.payload = FakeSM._Payload(data)

    class _Client:
        def __init__(self, outer):
            self._outer = outer

        def access_secret_version(self, name: str):
            raw = self._outer.store.get(name)
            if raw is None:
                raise RuntimeError(f"no secret at {name}")
            return FakeSM._Resp(raw.encode("utf-8"))

    def _get_client(self):
        return FakeSM._Client(self)

    def write(self, *, name: str, value: str, create_if_missing: bool = True):
        # Convention: path derived from name.
        path = f"projects/p/secrets/{name}/versions/latest"
        self.store[path] = value
        self.writes.append((name, value))
        return {
            "name": name,
            "path": path,
            "version_id": str(len(self.writes)),
            "created_secret": True,
        }


class StubRefresher(AnthropicOAuthRefresher):
    def __init__(self, new_access: str = "refreshed-access", fail: bool = False):
        super().__init__(http_client=object())  # pragma: no cover (unused)
        self._new_access = new_access
        self._fail = fail
        self.call_count = 0

    async def refresh(self, bundle):
        self.call_count += 1
        if self._fail:
            raise OAuthRefreshError("stub failure")
        return OAuthTokenBundle(
            access_token=self._new_access,
            refresh_token=bundle.refresh_token,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=8),
        )


def _seed_bundle(sm: FakeSM, path: str, *, expires_delta: timedelta, access="a", refresh="r"):
    b = OAuthTokenBundle(
        access_token=access,
        refresh_token=refresh,
        expires_at=datetime.now(timezone.utc) + expires_delta,
    )
    sm.store[path] = b.to_json()
    return b


@pytest.mark.asyncio
async def test_get_access_token_no_refresh_when_fresh():
    sm = FakeSM()
    path = "projects/p/secrets/watson-x/versions/latest"
    _seed_bundle(sm, path, expires_delta=timedelta(hours=4))
    ref = StubRefresher()
    mgr = OAuthTokenManager(sm_service=sm, refresher=ref)
    tok = await mgr.get_access_token(path)
    assert tok == "a"
    assert ref.call_count == 0


@pytest.mark.asyncio
async def test_get_access_token_refreshes_near_expiry_and_writes_sm():
    sm = FakeSM()
    path = "projects/p/secrets/watson-x/versions/latest"
    _seed_bundle(sm, path, expires_delta=timedelta(seconds=60))
    ref = StubRefresher(new_access="fresh-token")
    mgr = OAuthTokenManager(sm_service=sm, refresher=ref)
    tok = await mgr.get_access_token(path)
    assert tok == "fresh-token"
    assert ref.call_count == 1
    # SM write happened
    assert len(sm.writes) == 1
    written_name, written_val = sm.writes[0]
    assert written_name == "watson-x"
    assert "fresh-token" in written_val


@pytest.mark.asyncio
async def test_get_access_token_returns_stale_on_refresh_failure():
    sm = FakeSM()
    path = "projects/p/secrets/watson-x/versions/latest"
    _seed_bundle(sm, path, expires_delta=timedelta(seconds=10), access="stale-a")
    ref = StubRefresher(fail=True)
    mgr = OAuthTokenManager(sm_service=sm, refresher=ref)
    tok = await mgr.get_access_token(path)
    assert tok == "stale-a"
    # No successful write
    assert len(sm.writes) == 0


@pytest.mark.asyncio
async def test_ensure_fresh_skips_when_not_near_expiry():
    sm = FakeSM()
    path = "projects/p/secrets/watson-x/versions/latest"
    _seed_bundle(sm, path, expires_delta=timedelta(hours=3))
    ref = StubRefresher()
    mgr = OAuthTokenManager(sm_service=sm, refresher=ref)
    await mgr.ensure_fresh(path)
    assert ref.call_count == 0
    assert len(sm.writes) == 0


@pytest.mark.asyncio
async def test_ensure_fresh_refreshes_when_near_expiry():
    sm = FakeSM()
    path = "projects/p/secrets/watson-x/versions/latest"
    _seed_bundle(sm, path, expires_delta=timedelta(seconds=30))
    ref = StubRefresher()
    mgr = OAuthTokenManager(sm_service=sm, refresher=ref)
    await mgr.ensure_fresh(path)
    assert ref.call_count == 1
    assert len(sm.writes) == 1


@pytest.mark.asyncio
async def test_read_bundle_caches_within_ttl():
    sm = FakeSM()
    path = "projects/p/secrets/watson-x/versions/latest"
    _seed_bundle(sm, path, expires_delta=timedelta(hours=1), access="A")
    ref = StubRefresher()
    mgr = OAuthTokenManager(sm_service=sm, refresher=ref, cache_ttl_seconds=60)
    b1 = await mgr.read_bundle(path)
    # Mutate underlying SM — cache should shield until TTL elapses.
    _seed_bundle(sm, path, expires_delta=timedelta(hours=1), access="B")
    b2 = await mgr.read_bundle(path)
    assert b1 is not None and b2 is not None
    assert b1.access_token == "A"
    assert b2.access_token == "A"  # served from cache


@pytest.mark.asyncio
async def test_register_and_tracked_paths():
    sm = FakeSM()
    ref = StubRefresher()
    mgr = OAuthTokenManager(sm_service=sm, refresher=ref)
    await mgr.register("projects/p/secrets/a/versions/latest")
    await mgr.register("projects/p/secrets/b/versions/latest")
    await mgr.register("projects/p/secrets/a/versions/latest")  # dup
    paths = mgr.tracked_paths()
    assert len(paths) == 2
    assert "projects/p/secrets/a/versions/latest" in paths


@pytest.mark.asyncio
async def test_refresh_now_returns_none_without_refresh_token():
    sm = FakeSM()
    path = "projects/p/secrets/watson-x/versions/latest"
    # Seed a plain-string (legacy) value — no refresh_token.
    sm.store[path] = "legacy-plain-access-token"
    ref = StubRefresher()
    mgr = OAuthTokenManager(sm_service=sm, refresher=ref)
    result = await mgr.refresh_now(path)
    assert result is None
    assert ref.call_count == 0
