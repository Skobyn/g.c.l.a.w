"""Tests for ConnectionRepo Firestore CRUD."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from gclaw.firestore.connection_repo import ConnectionRepo
from gclaw.models.connection import Connection, ConnectionPermission, ConnectionStatus


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def repo(mock_db):
    return ConnectionRepo(db=mock_db, user_id="user_a")


def _make_connection(**kwargs) -> Connection:
    defaults = dict(
        id="conn_test",
        from_user_id="user_a",
        to_user_id="user_b",
        status=ConnectionStatus.PENDING,
        permission=ConnectionPermission.READ,
    )
    defaults.update(kwargs)
    return Connection(**defaults)


def test_create_calls_firestore_set(repo, mock_db):
    conn = _make_connection()
    result = repo.create(conn)
    assert result is conn
    mock_db.collection.assert_called_with("users")


def test_get_returns_none_when_not_exists(repo, mock_db):
    doc_mock = MagicMock()
    doc_mock.exists = False
    (
        mock_db.collection.return_value
        .document.return_value
        .collection.return_value
        .document.return_value
        .get.return_value
    ) = doc_mock
    result = repo.get("conn_missing")
    assert result is None


def test_get_returns_connection_when_exists(repo, mock_db):
    conn = _make_connection()
    doc_mock = MagicMock()
    doc_mock.exists = True
    doc_mock.id = "conn_test"
    doc_mock.to_dict.return_value = conn.to_firestore_dict()
    (
        mock_db.collection.return_value
        .document.return_value
        .collection.return_value
        .document.return_value
        .get.return_value
    ) = doc_mock
    result = repo.get("conn_test")
    assert result is not None
    assert result.id == "conn_test"
    assert result.from_user_id == "user_a"


def test_update_calls_firestore_set(repo, mock_db):
    conn = _make_connection(status=ConnectionStatus.ACTIVE)
    result = repo.update(conn)
    assert result is conn
    mock_db.collection.assert_called()


def test_delete_calls_firestore_delete(repo, mock_db):
    repo.delete("conn_test")
    (
        mock_db.collection.return_value
        .document.return_value
        .collection.return_value
        .document.return_value
        .delete.assert_called_once()
    )


def test_list_by_status_returns_connections(repo, mock_db):
    conn = _make_connection()
    doc_mock = MagicMock()
    doc_mock.id = "conn_test"
    doc_mock.to_dict.return_value = conn.to_firestore_dict()
    (
        mock_db.collection.return_value
        .document.return_value
        .collection.return_value
        .where.return_value
        .stream.return_value
    ) = [doc_mock]
    results = repo.list_by_status(ConnectionStatus.PENDING)
    assert len(results) == 1
    assert results[0].id == "conn_test"


def test_find_by_peer_returns_match(repo, mock_db):
    conn = _make_connection(status=ConnectionStatus.ACTIVE)
    doc_mock = MagicMock()
    doc_mock.id = "conn_test"
    doc_mock.to_dict.return_value = {
        **conn.to_firestore_dict(),
        "status": "active",
    }
    (
        mock_db.collection.return_value
        .document.return_value
        .collection.return_value
        .where.return_value
        .stream.return_value
    ) = [doc_mock]
    result = repo.find_by_peer("user_b")
    assert result is not None
    assert result.to_user_id == "user_b"


def test_find_by_peer_returns_none_when_no_match(repo, mock_db):
    (
        mock_db.collection.return_value
        .document.return_value
        .collection.return_value
        .where.return_value
        .stream.return_value
    ) = []
    result = repo.find_by_peer("user_unknown")
    assert result is None
