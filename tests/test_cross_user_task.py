"""Tests for cross-user task creation via A2A connections."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from gclaw.connection.service import ConnectionService
from gclaw.models.connection import (
    Connection,
    ConnectionPermission,
    ConnectionStatus,
)
from gclaw.models.task import BoardTask, TaskStatus


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def mock_board_repo_factory():
    """Factory that returns a mock BoardRepo for any user_id."""
    repos = {}

    def factory(user_id: str):
        if user_id not in repos:
            repo = MagicMock()
            repo.create.side_effect = lambda task: task
            repos[user_id] = repo
        return repos[user_id]

    return factory


@pytest.fixture
def service(mock_db, mock_board_repo_factory):
    return ConnectionService(
        db=mock_db,
        board_repo_factory=mock_board_repo_factory,
    )


def _active_conn_with_task_permission() -> Connection:
    return Connection(
        id="conn_test",
        from_user_id="user_a",
        to_user_id="user_b",
        status=ConnectionStatus.ACTIVE,
        permission=ConnectionPermission.TASK,
        shared_channel="user_a__user_b",
    )


class TestCreateTaskForPeer:
    def test_creates_task_on_peer_board(
        self, service, mock_board_repo_factory
    ):
        """With task permission, should create task on peer's board."""
        conn = _active_conn_with_task_permission()
        service._get_repo = MagicMock()
        repo_mock = MagicMock()
        repo_mock.get.return_value = conn
        service._get_repo.return_value = repo_mock

        task = service.create_task_for_peer(
            user_id="user_a",
            connection_id="conn_test",
            title="Review my PR",
            assignee="orchestrator",
            description="PR #42 needs review",
        )

        assert isinstance(task, BoardTask)
        assert task.title == "Review my PR"
        assert task.source.origin == "user_a"
        # Verify it was created on user_b's board
        peer_repo = mock_board_repo_factory("user_b")
        peer_repo.create.assert_called_once()

    def test_fails_without_task_permission(self, service):
        """With only read permission, task creation should be denied."""
        conn = Connection(
            id="conn_test",
            from_user_id="user_a",
            to_user_id="user_b",
            status=ConnectionStatus.ACTIVE,
            permission=ConnectionPermission.READ,
        )
        service._get_repo = MagicMock()
        repo_mock = MagicMock()
        repo_mock.get.return_value = conn
        service._get_repo.return_value = repo_mock

        with pytest.raises(PermissionError):
            service.create_task_for_peer(
                user_id="user_a",
                connection_id="conn_test",
                title="Review my PR",
                assignee="orchestrator",
            )

    def test_fails_on_inactive_connection(self, service):
        """Cannot create tasks on revoked connections."""
        conn = Connection(
            id="conn_test",
            from_user_id="user_a",
            to_user_id="user_b",
            status=ConnectionStatus.REVOKED,
            permission=ConnectionPermission.FULL,
        )
        service._get_repo = MagicMock()
        repo_mock = MagicMock()
        repo_mock.get.return_value = conn
        service._get_repo.return_value = repo_mock

        with pytest.raises(ValueError, match="not active"):
            service.create_task_for_peer(
                user_id="user_a",
                connection_id="conn_test",
                title="Review my PR",
                assignee="orchestrator",
            )
