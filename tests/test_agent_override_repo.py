"""Tests for AgentOverrideRepo with a Firestore fake."""

from __future__ import annotations

from gclaw.firestore.agent_override_repo import AgentOverrideRepo
from gclaw.models.agent_config import AgentIdentity, AgentOverride


class _FakeDoc:
    def __init__(self, data: dict | None, doc_id: str):
        self._data = data
        self.exists = data is not None
        self.id = doc_id

    def to_dict(self):
        return self._data


class _FakeDocRef:
    def __init__(self, coll, doc_id):
        self._coll = coll
        self._id = doc_id

    def set(self, data):
        self._coll._store[self._id] = dict(data)

    def get(self):
        return _FakeDoc(self._coll._store.get(self._id), self._id)

    def delete(self):
        self._coll._store.pop(self._id, None)


class _FakeCollection:
    def __init__(self):
        self._store: dict[str, dict] = {}

    def document(self, doc_id):
        return _FakeDocRef(self, doc_id)

    def stream(self):
        for doc_id, data in self._store.items():
            yield _FakeDoc(data, doc_id)


class _FakeChainDoc:
    def __init__(self, db, name):
        self._db = db
        self._name = name

    def collection(self, name):
        return self._db._get_sub(self._name, name)


class _FakeDb:
    def __init__(self):
        self._subs: dict[tuple[str, str], _FakeCollection] = {}

    def _get_sub(self, doc, sub):
        key = (doc, sub)
        if key not in self._subs:
            self._subs[key] = _FakeCollection()
        return self._subs[key]

    def collection(self, name):
        # We only use config/... for this test.
        class _Top:
            def __init__(self, db):
                self._db = db

            def document(self, doc_id):
                return _FakeChainDoc(self._db, doc_id)

        return _Top(self)


def test_create_get_update_delete_list():
    db = _FakeDb()
    repo = AgentOverrideRepo(db=db)

    o = AgentOverride(
        agent_name="dev-mgr",
        identity=AgentIdentity(display_name="Dev"),
    )
    repo.create(o)

    got = repo.get("dev-mgr")
    assert got is not None
    assert got.identity.display_name == "Dev"

    got.identity = AgentIdentity(display_name="Dev2")
    repo.update(got)
    again = repo.get("dev-mgr")
    assert again.identity.display_name == "Dev2"

    repo.create(AgentOverride(agent_name="foo"))
    listed = repo.list_all()
    assert {o.agent_name for o in listed} == {"dev-mgr", "foo"}

    repo.delete("foo")
    assert repo.get("foo") is None
    assert len(repo.list_all()) == 1


def test_get_missing_returns_none():
    db = _FakeDb()
    repo = AgentOverrideRepo(db=db)
    assert repo.get("nope") is None
