"""Tests for Postiz social media scheduling tools."""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from gclaw.tools import postiz_tools


@pytest.fixture(autouse=True)
def _configure_postiz():
    """Inject a test config before each test, clean up after."""
    postiz_tools.set_postiz_config(
        base_url="https://postiz.test",
        reviewer_url="https://reviewer.test",
        api_token="test-token-abc",
        channel_primary="ch-primary-123",
        channel_secondary="ch-secondary-456",
    )
    yield
    postiz_tools._config = {}


def _mock_response(status_code: int = 200, json_data=None, text: str = ""):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = text or json.dumps(json_data or {})
    return resp


# ---------- postiz_upload_image ----------


@pytest.mark.asyncio
async def test_upload_image_success(tmp_path):
    img = tmp_path / "test.png"
    img.write_bytes(b"\x89PNG fake image data")

    mock_resp = _mock_response(200, {"id": "img-1", "path": "https://cdn/img-1.png"})

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("gclaw.tools.postiz_tools.httpx.AsyncClient", return_value=mock_client):
        result = await postiz_tools.postiz_upload_image(str(img))

    assert "Uploaded: id=img-1 path=https://cdn/img-1.png" == result

    # Verify auth header has no Bearer prefix
    call_kwargs = mock_client.post.call_args
    assert call_kwargs.kwargs["headers"]["Authorization"] == "test-token-abc"
    assert "Bearer" not in call_kwargs.kwargs["headers"]["Authorization"]


@pytest.mark.asyncio
async def test_upload_returns_error_string_on_failure(tmp_path):
    img = tmp_path / "bad.png"
    img.write_bytes(b"data")

    mock_resp = _mock_response(403, text="Forbidden")
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("gclaw.tools.postiz_tools.httpx.AsyncClient", return_value=mock_client):
        result = await postiz_tools.postiz_upload_image(str(img))

    assert "failed" in result.lower()
    assert "403" in result


@pytest.mark.asyncio
async def test_upload_image_file_not_found():
    result = await postiz_tools.postiz_upload_image("/nonexistent/path.png")
    assert "file not found" in result.lower()


# ---------- postiz_create_draft ----------


@pytest.mark.asyncio
async def test_create_draft_success():
    mock_resp = _mock_response(
        200,
        [{"postId": "post-42", "integration": "ch-primary-123"}],
    )
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    images = json.dumps([{"id": "img-1", "path": "https://cdn/img-1.png"}])

    with patch("gclaw.tools.postiz_tools.httpx.AsyncClient", return_value=mock_client):
        result = await postiz_tools.postiz_create_draft(
            content="Hello LinkedIn!",
            image_ids_json=images,
            channel_id="ch-primary-123",
            date="2026-04-16T12:00:00.000Z",
        )

    assert "Draft created: postId=post-42" == result

    # Verify the exact payload shape sent to Postiz
    call_kwargs = mock_client.post.call_args
    sent_payload = call_kwargs.kwargs["json"]
    assert sent_payload["type"] == "draft"
    assert sent_payload["shortLink"] is False
    assert sent_payload["tags"] == []
    assert sent_payload["posts"][0]["integration"]["id"] == "ch-primary-123"
    assert sent_payload["posts"][0]["value"][0]["content"] == "Hello LinkedIn!"
    assert sent_payload["posts"][0]["value"][0]["image"] == [
        {"id": "img-1", "path": "https://cdn/img-1.png"}
    ]

    # Verify auth header — no Bearer prefix
    assert call_kwargs.kwargs["headers"]["Authorization"] == "test-token-abc"


@pytest.mark.asyncio
async def test_create_draft_default_channel():
    """When channel_id is empty, uses channel_primary from config."""
    mock_resp = _mock_response(200, [{"postId": "post-99"}])
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("gclaw.tools.postiz_tools.httpx.AsyncClient", return_value=mock_client):
        result = await postiz_tools.postiz_create_draft(
            content="Test post",
            image_ids_json="[]",
            channel_id="",  # empty — should default
        )

    assert "post-99" in result

    call_kwargs = mock_client.post.call_args
    sent_payload = call_kwargs.kwargs["json"]
    assert sent_payload["posts"][0]["integration"]["id"] == "ch-primary-123"


@pytest.mark.asyncio
async def test_create_draft_default_date():
    """When date is empty, defaults to now + 1 day."""
    mock_resp = _mock_response(200, [{"postId": "post-77"}])
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("gclaw.tools.postiz_tools.httpx.AsyncClient", return_value=mock_client):
        result = await postiz_tools.postiz_create_draft(
            content="Test",
        )

    assert "post-77" in result
    call_kwargs = mock_client.post.call_args
    sent_payload = call_kwargs.kwargs["json"]
    # The date should be a valid ISO string, not empty
    assert sent_payload["date"]
    assert "T" in sent_payload["date"]


# ---------- postiz_register_images ----------


@pytest.mark.asyncio
async def test_register_images_success():
    mock_resp = _mock_response(200, {"ok": True})
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    urls = json.dumps(["https://cdn/img-1.png", "https://cdn/img-2.png"])

    with patch("gclaw.tools.postiz_tools.httpx.AsyncClient", return_value=mock_client):
        result = await postiz_tools.postiz_register_images(
            post_id="post-42",
            image_urls_json=urls,
        )

    assert "Images registered for post post-42" == result

    # Verify payload
    call_kwargs = mock_client.post.call_args
    assert call_kwargs.kwargs["json"] == {
        "postId": "post-42",
        "images": ["https://cdn/img-1.png", "https://cdn/img-2.png"],
    }
    # Verify it hits the reviewer URL, not the base URL
    assert "reviewer.test" in call_kwargs.args[0]


@pytest.mark.asyncio
async def test_register_images_error():
    mock_resp = _mock_response(500, text="Internal error")
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("gclaw.tools.postiz_tools.httpx.AsyncClient", return_value=mock_client):
        result = await postiz_tools.postiz_register_images(
            post_id="post-42",
            image_urls_json='["https://img.png"]',
        )

    assert "failed" in result.lower()
    assert "500" in result


# ---------- postiz_upload_image_b64 ----------


@pytest.mark.asyncio
async def test_upload_image_b64_delegates():
    """b64 variant decodes, writes temp file, delegates to upload_image."""
    import base64

    fake_data = b"\x89PNG"
    b64 = base64.b64encode(fake_data).decode()

    with patch(
        "gclaw.tools.postiz_tools.postiz_upload_image",
        AsyncMock(return_value="Uploaded: id=img-b64 path=https://cdn/b64.png"),
    ) as mock_upload:
        result = await postiz_tools.postiz_upload_image_b64(b64, "generated.png")

    assert "img-b64" in result
    # Verify it was called with a path ending in the requested filename
    called_path = mock_upload.call_args.args[0]
    assert called_path.endswith("generated.png")


# ---------- not configured ----------


@pytest.mark.asyncio
async def test_tools_return_error_when_not_configured():
    postiz_tools._config = {}
    result = await postiz_tools.postiz_create_draft(content="test")
    assert "not configured" in result.lower()
