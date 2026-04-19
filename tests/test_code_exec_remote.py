"""Tests for the remote code-exec HTTP runner (Cloud Run sibling)."""

from __future__ import annotations

import httpx
import pytest

from gclaw.tools.catalog.models import CodeExecConfig
from gclaw.tools.code_exec.remote_runner import RemoteRunner


@pytest.mark.asyncio
async def test_remote_execute_posts_to_sandbox_url():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        import json
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "stdout": "hello",
                "stderr": "",
                "exit_code": 0,
                "duration_ms": 42,
                "truncated": False,
            },
        )

    runner = RemoteRunner(
        sandbox_url="https://gclaw-sandbox.example.com",
        identity_token_provider=lambda aud: "tok-" + aud,
        http_transport=httpx.MockTransport(handler),
    )
    out = await runner.execute(
        code="print('hello')",
        config=CodeExecConfig(runtime="python3.12", timeout_seconds=5),
    )
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/execute")
    assert captured["body"]["code"] == "print('hello')"
    assert captured["body"]["runtime"] == "python3.12"
    assert out["stdout"] == "hello"
    assert out["exit_code"] == 0


@pytest.mark.asyncio
async def test_remote_attaches_identity_jwt():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200, json={"stdout": "", "stderr": "", "exit_code": 0, "duration_ms": 0, "truncated": False})

    runner = RemoteRunner(
        sandbox_url="https://sandbox.example.com",
        identity_token_provider=lambda aud: "jwt-value",
        http_transport=httpx.MockTransport(handler),
    )
    await runner.execute(
        code="print(1)",
        config=CodeExecConfig(runtime="python3.12"),
    )
    assert captured["auth"] == "Bearer jwt-value"


@pytest.mark.asyncio
async def test_remote_http_error_surfaces_cleanly():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="sandbox on fire")

    runner = RemoteRunner(
        sandbox_url="https://sandbox.example.com",
        identity_token_provider=lambda aud: "tok",
        http_transport=httpx.MockTransport(handler),
    )
    out = await runner.execute(
        code="print(1)",
        config=CodeExecConfig(runtime="python3.12"),
    )
    assert out["exit_code"] != 0
    assert "500" in (out.get("error") or "")
