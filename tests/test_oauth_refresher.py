"""Tests for AnthropicOAuthRefresher."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from gclaw.catalog.oauth_tokens import (
    AnthropicOAuthRefresher,
    OAuthRefreshError,
    OAuthTokenBundle,
)


class FakeResponse:
    def __init__(self, *, status_code: int = 200, body: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._body = body or {}
        self.text = text or ""

    def json(self):
        return self._body


class FakeHttpClient:
    def __init__(self, response: FakeResponse):
        self._resp = response
        self.calls: list[dict] = []

    async def post(self, url: str, *, json=None, headers=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        return self._resp


def _bundle(refresh="orig-refresh"):
    return OAuthTokenBundle(
        access_token="old-access",
        refresh_token=refresh,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=30),
    )


@pytest.mark.asyncio
async def test_refresh_sends_correct_body():
    http = FakeHttpClient(FakeResponse(body={
        "access_token": "new-access",
        "refresh_token": "new-refresh",
        "expires_in": 3600,
    }))
    r = AnthropicOAuthRefresher(
        token_url="https://example/token",
        client_id="cid-123",
        http_client=http,
    )
    new = await r.refresh(_bundle())
    assert len(http.calls) == 1
    call = http.calls[0]
    assert call["url"] == "https://example/token"
    assert call["json"] == {
        "grant_type": "refresh_token",
        "refresh_token": "orig-refresh",
        "client_id": "cid-123",
    }
    assert new.access_token == "new-access"
    assert new.refresh_token == "new-refresh"
    remaining = (new.expires_at - datetime.now(timezone.utc)).total_seconds()
    assert 3500 < remaining < 3700


@pytest.mark.asyncio
async def test_refresh_reuses_old_refresh_token_when_response_omits_it():
    http = FakeHttpClient(FakeResponse(body={
        "access_token": "new-access",
        # no refresh_token in response
        "expires_in": 7200,
    }))
    r = AnthropicOAuthRefresher(http_client=http)
    new = await r.refresh(_bundle(refresh="carry-over"))
    assert new.refresh_token == "carry-over"


@pytest.mark.asyncio
async def test_refresh_raises_on_non_2xx():
    http = FakeHttpClient(FakeResponse(status_code=401, text="unauthorized"))
    r = AnthropicOAuthRefresher(http_client=http)
    with pytest.raises(OAuthRefreshError):
        await r.refresh(_bundle())


@pytest.mark.asyncio
async def test_refresh_requires_refresh_token():
    r = AnthropicOAuthRefresher(http_client=FakeHttpClient(FakeResponse()))
    bundle = OAuthTokenBundle(
        access_token="x",
        refresh_token="",
        expires_at=datetime.now(timezone.utc),
    )
    with pytest.raises(OAuthRefreshError):
        await r.refresh(bundle)


@pytest.mark.asyncio
async def test_refresh_raises_on_missing_access_token():
    http = FakeHttpClient(FakeResponse(body={"expires_in": 100}))
    r = AnthropicOAuthRefresher(http_client=http)
    with pytest.raises(OAuthRefreshError):
        await r.refresh(_bundle())


@pytest.mark.asyncio
async def test_refresh_preserves_unknown_response_fields_in_extra():
    http = FakeHttpClient(FakeResponse(body={
        "access_token": "a",
        "refresh_token": "r",
        "expires_in": 3600,
        "id_token": "jwt.xyz",
    }))
    r = AnthropicOAuthRefresher(http_client=http)
    new = await r.refresh(_bundle())
    assert new.extra.get("id_token") == "jwt.xyz"
