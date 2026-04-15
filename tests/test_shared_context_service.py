"""Tests for SharedContextService."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from gclaw.models.context_entry import ContextEntry
from gclaw.shared_context.service import INLINE_MAX_BYTES, SharedContextService


class FakeRepo:
    def __init__(self):
        self.store: dict[str, ContextEntry] = {}

    def create(self, entry):
        self.store[entry.id] = entry
        return entry

    def get(self, entry_id):
        return self.store.get(entry_id)

    def delete(self, entry_id):
        self.store.pop(entry_id, None)

    def list_by_namespace(self, namespace, limit=20, since=None):
        items = [e for e in self.store.values() if e.namespace == namespace]
        if since is not None:
            items = [e for e in items if e.timestamp >= since]
        items.sort(key=lambda e: e.timestamp, reverse=True)
        return items[:limit]

    def latest_in(self, namespace):
        items = self.list_by_namespace(namespace, limit=1)
        return items[0] if items else None

    def list_namespaces(self):
        buckets: dict = {}
        for e in self.store.values():
            b = buckets.setdefault(
                e.namespace,
                {"namespace": e.namespace, "count": 0, "latest_at": None},
            )
            b["count"] += 1
            if b["latest_at"] is None or e.timestamp > b["latest_at"]:
                b["latest_at"] = e.timestamp
        return list(buckets.values())


class FakeBlob:
    def __init__(self):
        self.uploaded: list[dict] = []
        self.deleted: list[str] = []

    def upload(self, *, namespace, entry_id, data, mime):
        url = f"gs://fake-bucket/{namespace}/{entry_id}"
        self.uploaded.append(
            {"namespace": namespace, "entry_id": entry_id, "data": data, "mime": mime, "url": url}
        )
        return url

    def signed_url(self, gs_url, *, minutes=15):
        return f"https://signed/{gs_url}?m={minutes}"

    def delete(self, gs_url):
        self.deleted.append(gs_url)


@pytest.fixture
def repo():
    return FakeRepo()


@pytest.fixture
def blob():
    return FakeBlob()


@pytest.fixture
def service(repo, blob):
    return SharedContextService(repo=repo, blob_store=blob)


def test_write_text_small_inlines(service, blob):
    e = service.write_text(namespace="feeds", content="hello", created_by="a")
    assert e.content == "hello"
    assert e.blob_url is None
    assert blob.uploaded == []


def test_write_text_big_goes_to_blob(service, blob):
    big = "x" * (INLINE_MAX_BYTES + 10)
    e = service.write_text(namespace="feeds", content=big, created_by="a")
    assert e.content is None
    assert e.blob_url == blob.uploaded[0]["url"]
    assert blob.uploaded[0]["mime"] == "text/markdown"


def test_write_text_no_blob_store_always_inlines(repo):
    svc = SharedContextService(repo=repo, blob_store=None)
    big = "x" * (INLINE_MAX_BYTES + 10)
    e = svc.write_text(namespace="feeds", content=big, created_by="a")
    assert e.content == big
    assert e.blob_url is None


def test_write_image_uses_blob(service, blob):
    e = service.write_image(
        namespace="charts",
        data=b"\x89PNG\r\n\x1a\n",
        mime="image/png",
        created_by="research",
    )
    assert e.blob_url is not None
    assert e.content is None
    assert blob.uploaded[0]["mime"] == "image/png"


def test_write_image_requires_blob(repo):
    svc = SharedContextService(repo=repo, blob_store=None)
    with pytest.raises(RuntimeError):
        svc.write_image(
            namespace="x", data=b"\x00", mime="image/png", created_by="a"
        )


def test_read_latest(service):
    service.write_text(namespace="feeds", content="old", created_by="a")
    # Slight delay via explicit timestamp so we control ordering
    e2 = ContextEntry(
        namespace="feeds", content="new", created_by="a",
        timestamp=datetime.now(timezone.utc),
    )
    service._repo.create(e2)
    latest = service.read_latest("feeds")
    assert latest is not None
    assert latest.content == "new"


def test_list_namespaces_aggregation(service):
    service.write_text(namespace="a", content="1", created_by="x")
    service.write_text(namespace="a", content="2", created_by="x")
    service.write_text(namespace="b", content="1", created_by="x")
    ns = service.list_namespaces()
    by_name = {b["namespace"]: b for b in ns}
    assert by_name["a"]["count"] == 2
    assert by_name["b"]["count"] == 1


def test_delete_also_removes_blob(service, blob):
    e = service.write_image(
        namespace="x", data=b"bin", mime="image/png", created_by="a"
    )
    service.delete(e.id)
    assert blob.deleted == [e.blob_url]
    assert service.get(e.id) is None


def test_signed_url_for(service):
    e = service.write_image(
        namespace="x", data=b"bin", mime="image/png", created_by="a"
    )
    url = service.signed_url_for(e)
    assert url and url.startswith("https://signed/")


def test_signed_url_for_inline(service):
    e = service.write_text(namespace="x", content="hi", created_by="a")
    assert service.signed_url_for(e) is None
