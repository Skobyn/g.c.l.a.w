"""Tests for the shared-context admin routes."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from gclaw.api.context_routes import init_context_router
from gclaw.models.context_entry import ContextEntry
from gclaw.shared_context.service import SharedContextService


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
def service():
    return SharedContextService(repo=FakeRepo(), blob_store=FakeBlob())


@pytest.fixture
def app(service):
    app = FastAPI()
    app.include_router(init_context_router(service))
    from gclaw.auth.dependencies import get_current_user_id
    app.dependency_overrides[get_current_user_id] = lambda: "test_user"
    return app


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_create_and_list_entry(client):
    resp = await client.post(
        "/admin/context",
        json={"namespace": "feeds", "content": "hello"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["namespace"] == "feeds"
    assert body["content"] == "hello"
    assert body["created_by"].startswith("admin:")

    resp = await client.get("/admin/context?namespace=feeds")
    assert resp.status_code == 200
    arr = resp.json()
    assert len(arr) == 1
    assert arr[0]["id"] == body["id"]


@pytest.mark.asyncio
async def test_list_namespaces(client):
    await client.post("/admin/context", json={"namespace": "a", "content": "1"})
    await client.post("/admin/context", json={"namespace": "a", "content": "2"})
    await client.post("/admin/context", json={"namespace": "b", "content": "1"})

    resp = await client.get("/admin/context/namespaces")
    assert resp.status_code == 200
    by_name = {b["namespace"]: b for b in resp.json()}
    assert by_name["a"]["count"] == 2
    assert by_name["b"]["count"] == 1


@pytest.mark.asyncio
async def test_get_entry(client):
    create = await client.post(
        "/admin/context", json={"namespace": "x", "content": "hi"}
    )
    eid = create.json()["id"]

    resp = await client.get(f"/admin/context/{eid}")
    assert resp.status_code == 200
    assert resp.json()["content"] == "hi"


@pytest.mark.asyncio
async def test_get_entry_404(client):
    resp = await client.get("/admin/context/ctx_notfound")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_entry(client):
    create = await client.post(
        "/admin/context", json={"namespace": "x", "content": "hi"}
    )
    eid = create.json()["id"]

    resp = await client.delete(f"/admin/context/{eid}")
    assert resp.status_code == 200
    assert resp.json() == {"deleted": True, "id": eid}

    resp = await client.get(f"/admin/context/{eid}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_404(client):
    resp = await client.delete("/admin/context/ctx_nope")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_blob_url_for_inline_returns_400(client):
    create = await client.post(
        "/admin/context", json={"namespace": "x", "content": "hi"}
    )
    eid = create.json()["id"]

    resp = await client.get(f"/admin/context/{eid}/blob")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_blob_url_happy_path(service, app):
    # Inject a blob-backed entry directly through the service.
    entry = service.write_image(
        namespace="charts", data=b"bin", mime="image/png", created_by="admin"
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/admin/context/{entry.id}/blob")
    assert resp.status_code == 200
    body = resp.json()
    assert body["expires_in_seconds"] == 900
    assert body["url"].startswith("https://signed/")


@pytest.mark.asyncio
async def test_list_with_since_bad_date(client):
    resp = await client.get(
        "/admin/context?namespace=x&since=not-a-date"
    )
    assert resp.status_code == 400
