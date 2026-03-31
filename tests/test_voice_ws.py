"""Tests for the voice WebSocket endpoint."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gclaw.api.voice_ws import init_voice_router


@pytest.fixture
def mock_genai_client():
    """Mock the google.genai Client for live API."""
    with patch("gclaw.voice.session.genai") as mock:
        mock_session = AsyncMock()
        mock_session.receive = AsyncMock(return_value=AsyncMock())
        mock_session.send_realtime_input = AsyncMock()
        mock_session.close = AsyncMock()

        mock_live = AsyncMock()
        mock_live.connect = AsyncMock()
        mock_live.connect.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_live.connect.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_client = MagicMock()
        mock_client.aio.live = mock_live
        mock.Client.return_value = mock_client

        yield mock_client


@pytest.fixture
def voice_app(mock_genai_client):
    app = FastAPI()
    app.include_router(init_voice_router(
        gemini_model="gemini-2.5-flash",
    ))
    return app


def test_voice_ws_rejects_without_token(voice_app):
    """WebSocket should reject connection without auth token."""
    client = TestClient(voice_app)
    with pytest.raises(Exception):
        with client.websocket_connect("/voice"):
            pass


def test_voice_ws_accepts_with_token(voice_app, mock_genai_client):
    """WebSocket should accept with valid auth token query param."""
    with patch("gclaw.api.voice_ws.verify_ws_token", return_value="test_user"):
        client = TestClient(voice_app)
        with client.websocket_connect("/voice?token=valid_token") as ws:
            # Connection established — close gracefully
            ws.close()
