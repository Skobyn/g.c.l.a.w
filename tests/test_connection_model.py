"""Tests for connection models."""

from __future__ import annotations

import pytest
from gclaw.models.connection import (
    Connection,
    ConnectionPermission,
    ConnectionStatus,
)


def test_connection_creation_defaults():
    """Connection should have sensible defaults."""
    conn = Connection(
        id="conn_abc123",
        from_user_id="user_a",
        to_user_id="user_b",
    )
    assert conn.status == ConnectionStatus.PENDING
    assert conn.permission == ConnectionPermission.READ
    assert conn.from_user_id == "user_a"
    assert conn.to_user_id == "user_b"
    assert conn.shared_channel == ""


def test_connection_permission_levels():
    """All four permission levels should be valid."""
    for level in ("read", "write", "task", "full"):
        perm = ConnectionPermission(level)
        assert perm.value == level


def test_connection_status_transitions():
    """Status should support pending, active, rejected, revoked."""
    for status in ("pending", "active", "rejected", "revoked"):
        s = ConnectionStatus(status)
        assert s.value == status


def test_connection_to_firestore_dict():
    """Should serialize to dict without id field."""
    conn = Connection(
        id="conn_abc",
        from_user_id="user_a",
        to_user_id="user_b",
        permission=ConnectionPermission.TASK,
        shared_channel="user_a__user_b",
    )
    d = conn.to_firestore_dict()
    assert "id" not in d
    assert d["from_user_id"] == "user_a"
    assert d["permission"] == "task"
    assert d["shared_channel"] == "user_a__user_b"


def test_connection_from_firestore_dict():
    """Should deserialize from Firestore doc."""
    data = {
        "from_user_id": "user_a",
        "to_user_id": "user_b",
        "status": "active",
        "permission": "write",
        "shared_channel": "user_a__user_b",
    }
    conn = Connection.from_firestore_dict("conn_xyz", data)
    assert conn.id == "conn_xyz"
    assert conn.status == ConnectionStatus.ACTIVE
    assert conn.permission == ConnectionPermission.WRITE


def test_connection_has_permission():
    """Permission hierarchy: full > task > write > read."""
    conn = Connection(
        id="c1",
        from_user_id="a",
        to_user_id="b",
        permission=ConnectionPermission.TASK,
    )
    assert conn.has_permission(ConnectionPermission.READ) is True
    assert conn.has_permission(ConnectionPermission.WRITE) is True
    assert conn.has_permission(ConnectionPermission.TASK) is True
    assert conn.has_permission(ConnectionPermission.FULL) is False
