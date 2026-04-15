"""Tests for OAuthTokenBundle parsing / serialization."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from gclaw.catalog.oauth_tokens import OAuthTokenBundle


def test_bundle_roundtrip_json():
    exp = datetime.now(timezone.utc) + timedelta(hours=8)
    b = OAuthTokenBundle(
        access_token="sk-ant-oat-xyz",
        refresh_token="sk-ant-ort-abc",
        expires_at=exp,
        token_type="Bearer",
        extra={"scope": "user"},
    )
    s = b.to_json()
    parsed = OAuthTokenBundle.parse(s)
    assert parsed is not None
    assert parsed.access_token == "sk-ant-oat-xyz"
    assert parsed.refresh_token == "sk-ant-ort-abc"
    assert parsed.token_type == "Bearer"
    # Extra round-trips.
    assert parsed.extra.get("scope") == "user"
    # Timestamp is close (may lose sub-second precision).
    assert abs((parsed.expires_at - exp).total_seconds()) < 2


def test_is_near_expiry_boundaries():
    now = datetime.now(timezone.utc)
    b_far = OAuthTokenBundle(
        access_token="a",
        refresh_token="r",
        expires_at=now + timedelta(hours=2),
    )
    assert b_far.is_near_expiry() is False
    assert b_far.is_near_expiry(margin_seconds=60) is False

    b_near = OAuthTokenBundle(
        access_token="a",
        refresh_token="r",
        expires_at=now + timedelta(seconds=60),
    )
    assert b_near.is_near_expiry(margin_seconds=600) is True

    b_expired = OAuthTokenBundle(
        access_token="a",
        refresh_token="r",
        expires_at=now - timedelta(minutes=5),
    )
    assert b_expired.is_near_expiry() is True


def test_parse_plain_string_fallback():
    b = OAuthTokenBundle.parse("plain-token-value")
    assert b is not None
    assert b.access_token == "plain-token-value"
    assert b.refresh_token == ""
    assert b.has_refresh_token() is False


def test_parse_none_and_empty():
    assert OAuthTokenBundle.parse(None) is None
    assert OAuthTokenBundle.parse("") is None
    assert OAuthTokenBundle.parse("   ") is None


def test_parse_accepts_expires_in():
    """Token endpoint responses contain expires_in (seconds), not expires_at."""
    payload = json.dumps({
        "access_token": "a",
        "refresh_token": "r",
        "expires_in": 3600,
    })
    b = OAuthTokenBundle.parse(payload)
    assert b is not None
    assert b.access_token == "a"
    remaining = (b.expires_at - datetime.now(timezone.utc)).total_seconds()
    assert 3500 < remaining < 3700


def test_parse_preserves_unknown_fields_in_extra():
    payload = json.dumps({
        "access_token": "a",
        "refresh_token": "r",
        "expires_in": 100,
        "id_token": "jwt.here",
        "scope": "chat:read",
    })
    b = OAuthTokenBundle.parse(payload)
    assert b is not None
    assert b.extra.get("id_token") == "jwt.here"
    assert b.extra.get("scope") == "chat:read"


def test_parse_invalid_json_returns_none():
    assert OAuthTokenBundle.parse("{not json") is None
