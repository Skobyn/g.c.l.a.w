"""Tests for onboarding API routes."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gclaw.api.onboarding_routes import init_onboarding_router
from gclaw.auth.dependencies import get_current_user_id


def _make_app(mock_onboarding_service: AsyncMock) -> FastAPI:
    app = FastAPI()
    app.include_router(init_onboarding_router(mock_onboarding_service))
    app.dependency_overrides[get_current_user_id] = lambda: "test_user"
    return app


@pytest.fixture
def mock_onboarding_service():
    return AsyncMock()


@pytest.fixture
def client(mock_onboarding_service):
    app = _make_app(mock_onboarding_service)
    return TestClient(app)


class TestStartOnboarding:
    def test_start_returns_intro(self, client, mock_onboarding_service):
        mock_onboarding_service.start_onboarding.return_value = {
            "step": "introduction",
            "message": "Welcome to GClaw!",
            "completed": False,
        }
        resp = client.post("/onboarding/start")
        assert resp.status_code == 200
        assert resp.json()["step"] == "introduction"


class TestAdvanceOnboarding:
    def test_advance_with_response(self, client, mock_onboarding_service):
        mock_onboarding_service.advance_onboarding.return_value = {
            "step": "daily_routines",
            "message": "Tell me about your daily routine.",
            "completed": False,
        }
        resp = client.post("/onboarding/advance", json={
            "response": "I prefer casual communication.",
        })
        assert resp.status_code == 200
        assert resp.json()["step"] == "daily_routines"


class TestOnboardingStatus:
    def test_status_returns_progress(self, client, mock_onboarding_service):
        mock_onboarding_service.get_status.return_value = {
            "completed": False,
            "current_step": "communication_style",
            "progress": 0.33,
        }
        resp = client.get("/onboarding/status")
        assert resp.status_code == 200
        assert resp.json()["progress"] == 0.33
