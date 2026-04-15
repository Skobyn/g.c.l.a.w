"""Tests for the OAuth-specific /admin/secrets/oauth endpoints."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from gclaw.api.secrets_routes import init_secrets_router
from gclaw.catalog.oauth_tokens import OAuthTokenBundle


class FakeSMService:
    def __init__(self):
        self.writes: list[dict] = []
        self._project = "p"

    @property
    def project(self):
        return self._project

    def normalize_name(self, name: str) -> str:
        return name if name.startswith("watson-") else f"watson-{name}"

    def write(self, *, name: str, value: str, create_if_missing: bool = True):
        norm = self.normalize_name(name)
        self.writes.append({"name": norm, "value": value})
        return {
            "name": norm,
            "path": f"projects/p/secrets/{norm}/versions/latest",
            "version_id": "1",
            "created_secret": True,
        }

    def rotate(self, *, name: str, value: str):
        return self.write(name=name, value=value)

    def list_gclaw_secrets(self):
        return []


class FakeOAuthManager:
    def __init__(self):
        self.registered: list[str] = []
        self.refresh_calls: list[str] = []
        self._refresh_result: OAuthTokenBundle | None = None

    async def register(self, sm_path: str) -> None:
        self.registered.append(sm_path)

    async def refresh_now(self, sm_path: str):
        self.refresh_calls.append(sm_path)
        return self._refresh_result


def _make_app(svc, mgr):
    app = FastAPI()
    app.include_router(init_secrets_router(svc, oauth_manager=mgr))
    from gclaw.auth.dependencies import get_current_user_id
    app.dependency_overrides[get_current_user_id] = lambda: "test_user"
    return app


@pytest.fixture
def svc():
    return FakeSMService()


@pytest.fixture
def mgr():
    return FakeOAuthManager()


@pytest.fixture
async def client(svc, mgr):
    app = _make_app(svc, mgr)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_write_oauth_secret_bundles_as_json(client, svc, mgr):
    resp = await client.post(
        "/admin/secrets/oauth",
        json={
            "name": "watson-claude-oauth",
            "access_token": "sk-ant-oat-abc",
            "refresh_token": "sk-ant-ort-xyz",
            "expires_in_seconds": 1800,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "watson-claude-oauth"
    assert body["path"].endswith("/versions/latest")

    # SM received a valid JSON bundle.
    assert len(svc.writes) == 1
    raw = svc.writes[0]["value"]
    parsed = OAuthTokenBundle.parse(raw)
    assert parsed is not None
    assert parsed.access_token == "sk-ant-oat-abc"
    assert parsed.refresh_token == "sk-ant-ort-xyz"
    remaining = (parsed.expires_at - datetime.now(timezone.utc)).total_seconds()
    assert 1700 < remaining < 1900

    # Newly created secret was auto-registered with the manager.
    assert body["path"] in mgr.registered


@pytest.mark.asyncio
async def test_write_oauth_secret_rejects_missing_tokens(client):
    resp = await client.post(
        "/admin/secrets/oauth",
        json={
            "name": "watson-foo",
            "access_token": "",
            "refresh_token": "r",
        },
    )
    # Validated by pydantic min_length=1 → 422.
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_refresh_now_triggers_manager(client, svc, mgr):
    mgr._refresh_result = OAuthTokenBundle(
        access_token="new",
        refresh_token="r",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=8),
    )
    resp = await client.post(
        "/admin/secrets/oauth/watson-x/refresh-now",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["refreshed"] is True
    assert body["expires_at"]
    assert mgr.refresh_calls == [
        "projects/p/secrets/watson-x/versions/latest",
    ]


@pytest.mark.asyncio
async def test_refresh_now_404_when_no_refresh_token(client, mgr):
    mgr._refresh_result = None
    resp = await client.post(
        "/admin/secrets/oauth/watson-x/refresh-now",
    )
    assert resp.status_code == 404
