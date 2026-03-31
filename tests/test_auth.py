"""Tests for Firebase Auth middleware and dependencies."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI, Depends
from starlette.requests import Request

from gclaw.auth.middleware import FirebaseAuthMiddleware
from gclaw.auth.dependencies import get_current_user_id


@pytest.fixture
def mock_verify_token():
    """Mock firebase_admin.auth.verify_id_token."""
    with patch("gclaw.auth.middleware.firebase_auth") as mock_auth:
        mock_auth.verify_id_token.return_value = {
            "uid": "test_user_123",
            "email": "test@example.com",
        }
        yield mock_auth


@pytest.fixture
def app_with_auth(mock_verify_token):
    """FastAPI app with auth middleware and a test endpoint."""
    app = FastAPI()
    app.add_middleware(FirebaseAuthMiddleware)

    @app.get("/protected")
    async def protected(request: Request):
        return {"user_id": request.state.user_id}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


@pytest.fixture
async def auth_client(app_with_auth):
    transport = ASGITransport(app=app_with_auth)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health_bypasses_auth(auth_client):
    """Health endpoint should not require auth."""
    resp = await auth_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_missing_auth_header_returns_401(auth_client):
    resp = await auth_client.get("/protected")
    assert resp.status_code == 401
    assert "missing" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_invalid_bearer_format_returns_401(auth_client):
    resp = await auth_client.get(
        "/protected",
        headers={"Authorization": "NotBearer token123"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_valid_token_sets_user_id(auth_client, mock_verify_token):
    resp = await auth_client.get(
        "/protected",
        headers={"Authorization": "Bearer valid_token_here"},
    )
    assert resp.status_code == 200
    assert resp.json()["user_id"] == "test_user_123"
    mock_verify_token.verify_id_token.assert_called_once_with("valid_token_here")


@pytest.mark.asyncio
async def test_expired_token_returns_401(auth_client, mock_verify_token):
    mock_verify_token.verify_id_token.side_effect = Exception("Token expired")
    resp = await auth_client.get(
        "/protected",
        headers={"Authorization": "Bearer expired_token"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_id_dependency():
    """Test the FastAPI dependency extracts user_id from request state."""
    mock_request = MagicMock()
    mock_request.state.user_id = "dep_user_456"
    user_id = await get_current_user_id(mock_request)
    assert user_id == "dep_user_456"


@pytest.mark.asyncio
async def test_get_current_user_id_missing_raises():
    """Test the dependency raises 401 when user_id is not set."""
    mock_request = MagicMock()
    mock_request.state = MagicMock(spec=[])  # no user_id attribute
    with pytest.raises(Exception):
        await get_current_user_id(mock_request)
