"""Tests for connection API routes."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gclaw.api.connection_routes import init_connection_router
from gclaw.auth.dependencies import get_current_user_id
from gclaw.models.connection import (
    Connection,
    ConnectionPermission,
    ConnectionStatus,
)


def _make_app(mock_connection_service: MagicMock) -> FastAPI:
    app = FastAPI()
    app.include_router(init_connection_router(mock_connection_service))
    # Override auth dependency so no real Firebase token is needed
    app.dependency_overrides[get_current_user_id] = lambda: "test_user"
    return app


@pytest.fixture
def mock_connection_service():
    return MagicMock()


@pytest.fixture
def client(mock_connection_service):
    app = _make_app(mock_connection_service)
    return TestClient(app)


class TestRequestEndpoint:
    def test_request_connection(self, client, mock_connection_service):
        conn = Connection(
            id="conn_123",
            from_user_id="test_user",
            to_user_id="other_user",
            status=ConnectionStatus.PENDING,
        )
        mock_connection_service.request_connection.return_value = conn

        resp = client.post("/connections/request", json={
            "to_user_id": "other_user",
            "permission": "read",
        })
        assert resp.status_code == 200
        assert resp.json()["id"] == "conn_123"
        assert resp.json()["status"] == "pending"

    def test_request_self_returns_400(self, client, mock_connection_service):
        mock_connection_service.request_connection.side_effect = ValueError(
            "Cannot connect to yourself"
        )
        resp = client.post("/connections/request", json={
            "to_user_id": "test_user",
            "permission": "read",
        })
        assert resp.status_code == 400


class TestAcceptEndpoint:
    def test_accept_connection(self, client, mock_connection_service):
        conn = Connection(
            id="conn_123",
            from_user_id="other",
            to_user_id="test_user",
            status=ConnectionStatus.ACTIVE,
            shared_channel="other__test_user",
        )
        mock_connection_service.accept_connection.return_value = conn

        resp = client.post("/connections/conn_123/accept")
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"


class TestListEndpoints:
    def test_list_active_connections(self, client, mock_connection_service):
        mock_connection_service.list_connections.return_value = []
        resp = client.get("/connections")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_pending_incoming(self, client, mock_connection_service):
        mock_connection_service.list_pending_incoming.return_value = []
        resp = client.get("/connections/incoming")
        assert resp.status_code == 200
        assert resp.json() == []


class TestRevokeEndpoint:
    def test_revoke_connection(self, client, mock_connection_service):
        conn = Connection(
            id="conn_123",
            from_user_id="test_user",
            to_user_id="other",
            status=ConnectionStatus.REVOKED,
        )
        mock_connection_service.revoke_connection.return_value = conn

        resp = client.post("/connections/conn_123/revoke")
        assert resp.status_code == 200
        assert resp.json()["status"] == "revoked"
