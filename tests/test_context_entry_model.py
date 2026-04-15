"""Tests for the ContextEntry model."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from gclaw.models.context_entry import ContextEntry


def test_defaults_populate():
    e = ContextEntry(namespace="feeds")
    assert e.namespace == "feeds"
    assert e.id.startswith("ctx_")
    assert e.content is None
    assert e.blob_url is None
    assert e.metadata == {}
    assert e.expires_at > datetime.now(timezone.utc) + timedelta(days=29)


def test_roundtrip_inline():
    e = ContextEntry(
        namespace="feeds",
        content="hello world",
        created_by="agent:feed-picker",
        metadata={"source": "rss"},
    )
    data = e.to_firestore_dict()
    assert "id" not in data
    assert data["namespace"] == "feeds"
    assert data["content"] == "hello world"

    restored = ContextEntry.from_firestore_dict(e.id, data)
    assert restored.id == e.id
    assert restored.content == "hello world"
    assert restored.created_by == "agent:feed-picker"
    assert restored.metadata == {"source": "rss"}


def test_roundtrip_blob():
    e = ContextEntry(
        namespace="hot-takes",
        blob_url="gs://bucket/hot-takes/2026-04-14/ctx_abc.md",
        blob_mime="text/markdown",
        created_by="agent:trends",
    )
    data = e.to_firestore_dict()
    restored = ContextEntry.from_firestore_dict(e.id, data)
    assert restored.blob_url == e.blob_url
    assert restored.blob_mime == "text/markdown"
    assert restored.content is None


def test_custom_expires_at():
    exp = datetime.now(timezone.utc) + timedelta(days=7)
    e = ContextEntry(namespace="x", expires_at=exp)
    assert e.expires_at == exp
