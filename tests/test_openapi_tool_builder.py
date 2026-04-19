"""Tests for the OpenAPI tool builder — auth, param mapping, response truncation."""

from __future__ import annotations

import json

import httpx
import pytest

from gclaw.tools.catalog.models import (
    ApiKeyAuth,
    BasicAuth,
    BearerAuth,
    NoAuth,
    OAuth2BearerAuth,
)
from gclaw.tools.openapi_mcp.loader import OperationDef, Parameter
from gclaw.tools.openapi_mcp.tool_builder import build_tool


def _op(method="GET", path="/pets/{petId}", operation_id="getPetById", **kw) -> OperationDef:
    return OperationDef(
        method=method,
        path=path,
        operation_id=operation_id,
        summary=kw.get("summary", ""),
        parameters=kw.get("parameters", []),
        request_body=kw.get("request_body"),
    )


def _mock_transport(handler):
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_path_params_interpolated():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"ok": True})

    op = _op(parameters=[Parameter(name="petId", location="path", required=True)])
    tool = build_tool(
        op,
        auth=NoAuth(),
        base_url="https://x",
        secret_resolver=lambda _ref: None,
        http_transport=_mock_transport(handler),
    )
    out = await tool(petId=42)
    assert captured["url"].endswith("/pets/42")
    assert '"ok": true' in out


@pytest.mark.asyncio
async def test_missing_required_param_returns_error():
    op = _op(parameters=[Parameter(name="petId", location="path", required=True)])
    tool = build_tool(
        op,
        auth=NoAuth(),
        base_url="https://x",
        secret_resolver=lambda _ref: None,
        http_transport=_mock_transport(lambda r: httpx.Response(200)),
    )
    out = await tool()
    assert "required" in out.lower()
    assert "petId" in out


@pytest.mark.asyncio
async def test_query_params_routed():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={})

    op = _op(
        method="GET",
        path="/pets",
        operation_id="findPetsByStatus",
        parameters=[Parameter(name="status", location="query", required=True)],
    )
    tool = build_tool(
        op,
        auth=NoAuth(),
        base_url="https://x",
        secret_resolver=lambda _ref: None,
        http_transport=_mock_transport(handler),
    )
    await tool(status="available")
    assert captured["params"] == {"status": "available"}


@pytest.mark.asyncio
async def test_post_body_serialized_as_json():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["content_type"] = request.headers.get("content-type", "")
        captured["body"] = json.loads(request.content.decode("utf-8") or "{}")
        return httpx.Response(201)

    op = _op(
        method="POST",
        path="/pets",
        operation_id="addPet",
        request_body={"required": True, "content": {"application/json": {"schema": {}}}},
    )
    tool = build_tool(
        op,
        auth=NoAuth(),
        base_url="https://x",
        secret_resolver=lambda _ref: None,
        http_transport=_mock_transport(handler),
    )
    await tool(body={"name": "fido", "tag": "dog"})
    assert captured["body"] == {"name": "fido", "tag": "dog"}
    assert captured["content_type"].startswith("application/json")


@pytest.mark.asyncio
async def test_auth_api_key_header():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = {k.lower(): v for k, v in request.headers.items()}
        return httpx.Response(200)

    op = _op(parameters=[Parameter(name="petId", location="path", required=True)])
    tool = build_tool(
        op,
        auth=ApiKeyAuth(location="header", param_name="X-API-Key", credential_ref="ref"),
        base_url="https://x",
        secret_resolver=lambda ref: "SEKRET",
        http_transport=_mock_transport(handler),
    )
    await tool(petId=1)
    assert captured["headers"]["x-api-key"] == "SEKRET"


@pytest.mark.asyncio
async def test_auth_api_key_query():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200)

    op = _op(
        method="GET",
        path="/pets",
        operation_id="findPetsByStatus",
        parameters=[Parameter(name="status", location="query", required=True)],
    )
    tool = build_tool(
        op,
        auth=ApiKeyAuth(location="query", param_name="apikey", credential_ref="ref"),
        base_url="https://x",
        secret_resolver=lambda ref: "K",
        http_transport=_mock_transport(handler),
    )
    await tool(status="avail")
    assert captured["params"] == {"status": "avail", "apikey": "K"}


@pytest.mark.asyncio
async def test_auth_bearer():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200)

    op = _op(parameters=[Parameter(name="petId", location="path", required=True)])
    tool = build_tool(
        op,
        auth=BearerAuth(credential_ref="ref"),
        base_url="https://x",
        secret_resolver=lambda ref: "tok123",
        http_transport=_mock_transport(handler),
    )
    await tool(petId=1)
    assert captured["auth"] == "Bearer tok123"


@pytest.mark.asyncio
async def test_auth_oauth2_uses_same_bearer_header():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200)

    op = _op(parameters=[Parameter(name="petId", location="path", required=True)])
    tool = build_tool(
        op,
        auth=OAuth2BearerAuth(credential_ref="ref"),
        base_url="https://x",
        secret_resolver=lambda ref: "oauth_tok",
        http_transport=_mock_transport(handler),
    )
    await tool(petId=1)
    assert captured["auth"] == "Bearer oauth_tok"


@pytest.mark.asyncio
async def test_auth_basic():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200)

    op = _op(parameters=[Parameter(name="petId", location="path", required=True)])
    tool = build_tool(
        op,
        auth=BasicAuth(credential_ref="ref"),
        base_url="https://x",
        secret_resolver=lambda ref: "user:pass",
        http_transport=_mock_transport(handler),
    )
    await tool(petId=1)
    # httpx emits lowercase "basic"; credential is base64(user:pass)=dXNlcjpwYXNz
    assert captured["auth"].lower().startswith("basic ")
    assert "dXNlcjpwYXNz" in captured["auth"]


@pytest.mark.asyncio
async def test_response_truncated_past_cap():
    huge = "x" * 20000

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=huge)

    op = _op(parameters=[Parameter(name="petId", location="path", required=True)])
    tool = build_tool(
        op,
        auth=NoAuth(),
        base_url="https://x",
        secret_resolver=lambda _ref: None,
        http_transport=_mock_transport(handler),
    )
    out = await tool(petId=1)
    # Cap is 16 KB; expect a truncation marker in the output.
    assert len(out) <= 16 * 1024 + 200
    assert "truncated" in out.lower()


@pytest.mark.asyncio
async def test_http_error_returned_as_string():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "not found"})

    op = _op(parameters=[Parameter(name="petId", location="path", required=True)])
    tool = build_tool(
        op,
        auth=NoAuth(),
        base_url="https://x",
        secret_resolver=lambda _ref: None,
        http_transport=_mock_transport(handler),
    )
    out = await tool(petId=1)
    assert "404" in out
    # Body still surfaces so the LLM has something to reason about
    assert "not found" in out.lower()
