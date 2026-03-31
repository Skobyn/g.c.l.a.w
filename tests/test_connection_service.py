"""Tests for the ConnectionService."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from gclaw.connection.service import ConnectionService
from gclaw.models.connection import (
    Connection,
    ConnectionPermission,
    ConnectionStatus,
)


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def service(mock_db):
    return ConnectionService(db=mock_db)


def _make_pending_conn(
    from_user: str = "user_a",
    to_user: str = "user_b",
) -> Connection:
    return Connection(
        id="conn_test",
        from_user_id=from_user,
        to_user_id=to_user,
        status=ConnectionStatus.PENDING,
        permission=ConnectionPermission.READ,
    )


class TestRequestConnection:
    def test_creates_bilateral_records(self, service, mock_db):
        """Request should create a record in both users' subcollections."""
        conn = service.request_connection(
            from_user_id="user_a",
            to_user_id="user_b",
            permission=ConnectionPermission.WRITE,
        )
        assert conn.from_user_id == "user_a"
        assert conn.to_user_id == "user_b"
        assert conn.status == ConnectionStatus.PENDING
        assert conn.permission == ConnectionPermission.WRITE
        # Both repos should have had create() called
        assert mock_db.collection.call_count >= 2

    def test_rejects_self_connection(self, service):
        """Cannot connect to yourself."""
        with pytest.raises(ValueError, match="Cannot connect to yourself"):
            service.request_connection(
                from_user_id="user_a",
                to_user_id="user_a",
            )


class TestAcceptConnection:
    def test_accept_sets_active_and_creates_shared_channel(
        self, service, mock_db
    ):
        """Accept should set both records to active with shared_channel."""
        pending = _make_pending_conn()
        # Mock the repo to return the pending connection
        service._get_repo = MagicMock()
        repo_mock = MagicMock()
        repo_mock.get.return_value = pending
        service._get_repo.return_value = repo_mock

        result = service.accept_connection(
            user_id="user_b",
            connection_id="conn_test",
        )
        assert result.status == ConnectionStatus.ACTIVE
        assert result.shared_channel != ""

    def test_accept_rejects_if_not_recipient(self, service):
        """Only the recipient can accept."""
        pending = _make_pending_conn()
        service._get_repo = MagicMock()
        repo_mock = MagicMock()
        repo_mock.get.return_value = pending
        service._get_repo.return_value = repo_mock

        with pytest.raises(
            ValueError, match="Only the recipient can accept"
        ):
            service.accept_connection(
                user_id="user_a",  # sender, not recipient
                connection_id="conn_test",
            )


class TestRejectConnection:
    def test_reject_sets_rejected_status(self, service):
        """Reject should set status to rejected on both records."""
        pending = _make_pending_conn()
        service._get_repo = MagicMock()
        repo_mock = MagicMock()
        repo_mock.get.return_value = pending
        service._get_repo.return_value = repo_mock

        result = service.reject_connection(
            user_id="user_b",
            connection_id="conn_test",
        )
        assert result.status == ConnectionStatus.REJECTED


class TestRevokeConnection:
    def test_revoke_sets_revoked_status(self, service):
        """Either user can revoke an active connection."""
        active = Connection(
            id="conn_test",
            from_user_id="user_a",
            to_user_id="user_b",
            status=ConnectionStatus.ACTIVE,
            shared_channel="user_a__user_b",
        )
        service._get_repo = MagicMock()
        repo_mock = MagicMock()
        repo_mock.get.return_value = active
        service._get_repo.return_value = repo_mock

        result = service.revoke_connection(
            user_id="user_a",
            connection_id="conn_test",
        )
        assert result.status == ConnectionStatus.REVOKED


class TestPermissionEnforcement:
    def test_check_permission_passes(self, service):
        """Should not raise when permission is sufficient."""
        active = Connection(
            id="c1",
            from_user_id="a",
            to_user_id="b",
            status=ConnectionStatus.ACTIVE,
            permission=ConnectionPermission.TASK,
        )
        service._get_repo = MagicMock()
        repo_mock = MagicMock()
        repo_mock.get.return_value = active
        service._get_repo.return_value = repo_mock

        # Should not raise
        service.check_permission(
            user_id="a",
            connection_id="c1",
            required=ConnectionPermission.WRITE,
        )

    def test_check_permission_fails(self, service):
        """Should raise when permission is insufficient."""
        active = Connection(
            id="c1",
            from_user_id="a",
            to_user_id="b",
            status=ConnectionStatus.ACTIVE,
            permission=ConnectionPermission.READ,
        )
        service._get_repo = MagicMock()
        repo_mock = MagicMock()
        repo_mock.get.return_value = active
        service._get_repo.return_value = repo_mock

        with pytest.raises(PermissionError):
            service.check_permission(
                user_id="a",
                connection_id="c1",
                required=ConnectionPermission.WRITE,
            )
