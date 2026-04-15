"""Tests for shared-context agent tools."""

from __future__ import annotations

import base64
import json

import pytest

from gclaw.models.context_entry import ContextEntry
from gclaw.shared_context.service import SharedContextService
from gclaw.tools import context_tools


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


@pytest.fixture(autouse=True)
def _reset_service():
    context_tools.set_context_service(None)
    yield
    context_tools.set_context_service(None)


@pytest.fixture
def service():
    svc = SharedContextService(repo=FakeRepo(), blob_store=FakeBlob())
    context_tools.set_context_service(svc)
    return svc


async def test_write_missing_service_returns_error_string():
    out = await context_tools.context_write("feeds", "hi")
    assert isinstance(out, str)
    assert out.startswith("context_write failed")


async def test_write_happy_path(service):
    out = await context_tools.context_write(
        "feeds", "hello", metadata_json='{"src": "rss"}'
    )
    assert "Wrote context entry" in out
    assert "feeds" in out


async def test_write_invalid_metadata_is_ignored(service):
    out = await context_tools.context_write(
        "feeds", "hello", metadata_json="not-json"
    )
    # Should not fail — bad metadata silently dropped.
    assert "Wrote context entry" in out


async def test_read_latest_empty(service):
    out = await context_tools.context_read_latest("nowhere")
    assert "No entries" in out


async def test_read_latest_inline(service):
    await context_tools.context_write("feeds", "hello world")
    out = await context_tools.context_read_latest("feeds")
    assert "hello world" in out


async def test_read_latest_blob(service):
    # Manually write an image so read_latest returns a blob entry
    service.write_image(
        namespace="charts", data=b"binary", mime="image/png", created_by="a"
    )
    out = await context_tools.context_read_latest("charts")
    assert "blob" in out.lower()
    assert "https://signed/" in out or "gs://" in out


async def test_list_empty(service):
    out = await context_tools.context_list("nope")
    assert "No entries" in out


async def test_list_formats_rows(service):
    await context_tools.context_write("feeds", "one")
    await context_tools.context_write("feeds", "two")
    out = await context_tools.context_list("feeds", limit=5)
    lines = out.splitlines()
    assert len(lines) == 2
    for line in lines:
        assert line.startswith("[")
        assert "(ctx_" in line


async def test_write_image_happy_path(service):
    b64 = base64.b64encode(b"binary-data").decode("ascii")
    out = await context_tools.context_write_image(
        "charts", b64, mime="image/png"
    )
    assert "Wrote image entry" in out
    assert "gs://" in out


async def test_write_image_bad_base64_returns_error_string(service):
    out = await context_tools.context_write_image(
        "charts", "not!!!base64###", mime="image/png"
    )
    # base64 is lenient — but if it does fail, we must return a string.
    assert isinstance(out, str)


async def test_write_image_missing_service_returns_error_string():
    b64 = base64.b64encode(b"x").decode("ascii")
    out = await context_tools.context_write_image("x", b64)
    assert out.startswith("context_write_image failed")


async def test_tools_never_raise_on_any_input():
    """No matter what we throw in, tools must return strings."""
    for out in (
        await context_tools.context_write("", ""),
        await context_tools.context_read_latest(""),
        await context_tools.context_list(""),
        await context_tools.context_write_image("", ""),
    ):
        assert isinstance(out, str)


async def test_metadata_json_dict_is_parsed(service):
    md = json.dumps({"trend": "ai", "score": 0.9})
    out = await context_tools.context_write("trends", "body", metadata_json=md)
    assert "Wrote context entry" in out
    latest = service.read_latest("trends")
    assert latest is not None
    assert latest.metadata == {"trend": "ai", "score": 0.9}
