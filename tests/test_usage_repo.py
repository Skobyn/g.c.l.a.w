"""UsageRepo CRUD + aggregation on an in-memory fake Firestore."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from gclaw.firestore.usage_repo import UsageRepo
from gclaw.models.usage import UsageEvent, UsageKind


# --- in-memory fake Firestore ----------------------------------------------


class _Doc:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = True

    def to_dict(self):
        return dict(self._data)


class _Query:
    def __init__(self, docs, filters=None, order=None, limit=None):
        self._docs = docs
        self._filters = filters or []
        self._order = order
        self._limit = limit

    def where(self, field, op, value):
        return _Query(self._docs, self._filters + [(field, op, value)],
                      self._order, self._limit)

    def order_by(self, field, direction=None):
        return _Query(self._docs, self._filters, (field, direction), self._limit)

    def limit(self, n):
        return _Query(self._docs, self._filters, self._order, n)

    def _apply(self):
        rows = list(self._docs.items())
        for field, op, val in self._filters:
            def match(d):
                v = d[1].get(field)
                if op == "==":
                    return v == val
                # Coerce datetime ↔ iso-string for filter comparisons
                if isinstance(v, str) and hasattr(val, "isoformat"):
                    try:
                        v = datetime.fromisoformat(v.replace("Z", "+00:00"))
                    except ValueError:
                        return False
                if op == ">=":
                    return v is not None and v >= val
                if op == "<=":
                    return v is not None and v <= val
                return False
            rows = [r for r in rows if match(r)]
        if self._order:
            field, direction = self._order
            # direction=None → asc; treat "DESCENDING" token as desc
            reverse = (direction is not None
                       and str(direction).upper().endswith("DESCENDING"))
            rows.sort(key=lambda r: r[1].get(field), reverse=reverse)
        if self._limit is not None:
            rows = rows[: self._limit]
        return rows

    def stream(self):
        return [_Doc(k, v) for k, v in self._apply()]


class _Collection:
    def __init__(self, store):
        self._store = store

    def document(self, doc_id):
        col = self

        class _DocRef:
            def set(inner, data):
                col._store[doc_id] = dict(data)

            def get(inner):
                if doc_id in col._store:
                    return _Doc(doc_id, col._store[doc_id])
                d = _Doc(doc_id, {})
                d.exists = False
                return d

            def delete(inner):
                col._store.pop(doc_id, None)

            def collection(inner, _name):
                raise AssertionError("not used")

        return _DocRef()

    def where(self, field, op, value):
        return _Query(self._store, [(field, op, value)])

    def order_by(self, field, direction=None):
        return _Query(self._store, [], (field, direction))

    def stream(self):
        return _Query(self._store).stream()


class _FakeClient:
    def __init__(self):
        self._users: dict[str, dict[str, dict]] = {}

    def collection(self, name):
        assert name == "users"

        class _UsersCol:
            def document(inner, user_id):
                outer = self
                outer._users.setdefault(user_id, {})

                class _UserDoc:
                    def collection(inner2, subname):
                        assert subname == "usage"
                        outer._users[user_id].setdefault("usage", {})
                        return _Collection(outer._users[user_id]["usage"])

                return _UserDoc()

        return _UsersCol()


@pytest.fixture
def repo():
    return UsageRepo(db=_FakeClient(), user_id="u1")


def test_record_writes_with_expires_at(repo):
    ev = UsageEvent(kind=UsageKind.MODEL, name="m1")
    repo.record(ev)
    store = repo._db._users["u1"]["usage"]
    assert ev.id in store
    assert "expires_at" in store[ev.id]


def test_list_recent_newest_first(repo):
    now = datetime.now(timezone.utc)
    old = UsageEvent(kind=UsageKind.AGENT, name="old",
                     timestamp=now - timedelta(hours=2))
    mid = UsageEvent(kind=UsageKind.AGENT, name="mid",
                     timestamp=now - timedelta(hours=1))
    new = UsageEvent(kind=UsageKind.AGENT, name="new", timestamp=now)
    for e in (old, mid, new):
        repo.record(e)
    events = repo.list_recent(limit=10)
    assert [e.name for e in events] == ["new", "mid", "old"]


def test_list_recent_filter_kind(repo):
    for e in (
        UsageEvent(kind=UsageKind.MODEL, name="m"),
        UsageEvent(kind=UsageKind.AGENT, name="a"),
        UsageEvent(kind=UsageKind.TOOL, name="t"),
    ):
        repo.record(e)
    tool_events = repo.list_recent(kind=UsageKind.TOOL)
    assert len(tool_events) == 1
    assert tool_events[0].name == "t"


def test_aggregate_by_name(repo):
    now = datetime.now(timezone.utc)
    for i in range(3):
        repo.record(UsageEvent(
            kind=UsageKind.MODEL,
            name="flash",
            tokens_in=10,
            tokens_out=5,
            cost_usd=0.01,
            timestamp=now,
        ))
    repo.record(UsageEvent(
        kind=UsageKind.MODEL, name="pro", tokens_in=100, tokens_out=50,
        cost_usd=0.5, timestamp=now,
    ))
    # Different kind shouldn't be mixed in
    repo.record(UsageEvent(kind=UsageKind.AGENT, name="flash", timestamp=now))

    rows = repo.aggregate_by_name(
        UsageKind.MODEL, since=now - timedelta(minutes=5)
    )
    by_name = {r["name"]: r for r in rows}
    assert by_name["flash"]["count"] == 3
    assert by_name["flash"]["tokens_in"] == 30
    assert by_name["flash"]["tokens_out"] == 15
    assert by_name["pro"]["count"] == 1
    # Most-frequent first
    assert rows[0]["name"] == "flash"


def test_aggregate_by_hour(repo):
    base = datetime(2026, 4, 14, 10, 0, tzinfo=timezone.utc)
    repo.record(UsageEvent(kind=UsageKind.MODEL, name="m", timestamp=base,
                           cost_usd=0.1))
    repo.record(UsageEvent(kind=UsageKind.AGENT, name="a",
                           timestamp=base + timedelta(minutes=30)))
    repo.record(UsageEvent(kind=UsageKind.TOOL, name="t",
                           timestamp=base + timedelta(hours=1, minutes=15)))

    rows = repo.aggregate_by_hour(since=base - timedelta(hours=1))
    assert len(rows) == 2
    first = rows[0]
    assert first["model_count"] == 1
    assert first["agent_count"] == 1
    assert first["cost_usd"] == 0.1
    second = rows[1]
    assert second["tool_count"] == 1
