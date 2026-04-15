"""Tests for ContextEntryRepo using an in-memory fake Firestore client."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from gclaw.firestore.context_entry_repo import ContextEntryRepo
from gclaw.models.context_entry import ContextEntry


# --- Fake Firestore ---------------------------------------------------------


class _FakeDocSnap:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data else None


class _FakeDocRef:
    def __init__(self, store: dict, doc_id: str):
        self._store = store
        self._id = doc_id

    def set(self, data):
        self._store[self._id] = dict(data)

    def delete(self):
        self._store.pop(self._id, None)

    def get(self):
        return _FakeDocSnap(self._id, self._store.get(self._id))


class _FakeQuery:
    def __init__(self, store: dict, filters: list | None = None):
        self._store = store
        self._filters = filters or []

    def where(self, field, op, value):
        return _FakeQuery(self._store, self._filters + [(field, op, value)])

    def stream(self):
        for doc_id, data in self._store.items():
            ok = True
            for field, op, value in self._filters:
                v = data.get(field)
                if op == "==":
                    if v != value:
                        ok = False
                        break
                elif op == ">=":
                    if v is None or v < value:
                        ok = False
                        break
            if ok:
                yield _FakeDocSnap(doc_id, data)


class _FakeCollection:
    def __init__(self, store: dict):
        self._store = store

    def document(self, doc_id):
        return _FakeDocRef(self._store, doc_id)

    def stream(self):
        return _FakeQuery(self._store).stream()

    def where(self, field, op, value):
        return _FakeQuery(self._store).where(field, op, value)


class _FakeSubDoc:
    def __init__(self, subcollections: dict):
        self._subs = subcollections

    def collection(self, name):
        store = self._subs.setdefault(name, {})
        return _FakeCollection(store)


class _FakeRoot:
    def __init__(self):
        self._docs: dict = {}

    def document(self, name):
        sub = self._docs.setdefault(name, {})
        return _FakeSubDoc(sub)


class FakeFirestoreClient:
    def __init__(self):
        self._cols: dict = {}

    def collection(self, name):
        root = self._cols.setdefault(name, _FakeRoot())
        return root


@pytest.fixture
def repo():
    db = FakeFirestoreClient()
    return ContextEntryRepo(db=db)


def test_create_and_get(repo):
    entry = ContextEntry(namespace="feeds", content="hello", created_by="a")
    repo.create(entry)
    got = repo.get(entry.id)
    assert got is not None
    assert got.content == "hello"
    assert got.namespace == "feeds"


def test_get_missing(repo):
    assert repo.get("ctx_missing") is None


def test_delete(repo):
    e = ContextEntry(namespace="x", content="y")
    repo.create(e)
    repo.delete(e.id)
    assert repo.get(e.id) is None


def test_list_by_namespace_sorted_desc(repo):
    now = datetime.now(timezone.utc)
    e1 = ContextEntry(
        namespace="feeds", content="old", timestamp=now - timedelta(hours=2)
    )
    e2 = ContextEntry(
        namespace="feeds", content="new", timestamp=now - timedelta(hours=1)
    )
    e3 = ContextEntry(namespace="other", content="nope", timestamp=now)
    for e in (e1, e2, e3):
        repo.create(e)
    out = repo.list_by_namespace("feeds")
    assert [e.content for e in out] == ["new", "old"]


def test_list_by_namespace_since(repo):
    now = datetime.now(timezone.utc)
    e1 = ContextEntry(
        namespace="feeds", content="old", timestamp=now - timedelta(days=2)
    )
    e2 = ContextEntry(
        namespace="feeds", content="new", timestamp=now - timedelta(hours=1)
    )
    for e in (e1, e2):
        repo.create(e)
    out = repo.list_by_namespace("feeds", since=now - timedelta(hours=2))
    assert [e.content for e in out] == ["new"]


def test_latest_in(repo):
    now = datetime.now(timezone.utc)
    e1 = ContextEntry(namespace="feeds", content="old", timestamp=now - timedelta(hours=1))
    e2 = ContextEntry(namespace="feeds", content="new", timestamp=now)
    repo.create(e1)
    repo.create(e2)
    latest = repo.latest_in("feeds")
    assert latest is not None
    assert latest.content == "new"


def test_latest_in_empty(repo):
    assert repo.latest_in("nothing") is None


def test_list_namespaces(repo):
    now = datetime.now(timezone.utc)
    repo.create(ContextEntry(namespace="a", timestamp=now - timedelta(hours=1)))
    repo.create(ContextEntry(namespace="a", timestamp=now))
    repo.create(ContextEntry(namespace="b", timestamp=now - timedelta(hours=2)))
    ns = repo.list_namespaces()
    buckets = {b["namespace"]: b for b in ns}
    assert buckets["a"]["count"] == 2
    assert buckets["b"]["count"] == 1
    assert buckets["a"]["latest_at"] == now


def test_delete_expired(repo):
    now = datetime.now(timezone.utc)
    fresh = ContextEntry(namespace="x", content="live")
    fresh.expires_at = now + timedelta(days=1)
    expired = ContextEntry(namespace="x", content="dead")
    expired.expires_at = now - timedelta(days=1)
    repo.create(fresh)
    repo.create(expired)
    deleted = repo.delete_expired(now=now)
    assert deleted == 1
    assert repo.get(fresh.id) is not None
    assert repo.get(expired.id) is None
