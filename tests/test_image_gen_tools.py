"""Tests for image generation tools."""

from __future__ import annotations

import base64
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from gclaw.tools import image_gen_tools


def _make_png_bytes() -> bytes:
    """Tiny valid PNG for tests."""
    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (2, 2), (255, 0, 0)).save(buf, "PNG")
    return buf.getvalue()


def _mock_genai_response(image_bytes: bytes):
    """Build a mock genai response with one image part."""
    inline = MagicMock()
    inline.data = image_bytes
    image_part = MagicMock()
    image_part.text = None
    image_part.inline_data = inline

    response = MagicMock()
    response.parts = [image_part]
    return response


def test_generate_image_no_api_key_returns_error(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(image_gen_tools, "_TMP_DIR", tmp_path)

    import asyncio
    result = asyncio.run(image_gen_tools.generate_image("a cat"))
    assert "GEMINI_API_KEY not set" in result


def test_generate_image_empty_prompt(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    monkeypatch.setattr(image_gen_tools, "_TMP_DIR", tmp_path)

    import asyncio
    result = asyncio.run(image_gen_tools.generate_image(""))
    assert "prompt is empty" in result


def test_generate_image_success_saves_png(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    monkeypatch.setattr(image_gen_tools, "_TMP_DIR", tmp_path)

    png = _make_png_bytes()
    fake_response = _mock_genai_response(png)
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_response

    with patch("google.genai.Client", return_value=fake_client):
        import asyncio
        result = asyncio.run(
            image_gen_tools.generate_image(
                "clean infographic", filename="test-out.png"
            )
        )

    assert result.endswith("test-out.png")
    assert (tmp_path / "test-out.png").exists()
    # Verify resolution was passed
    call = fake_client.models.generate_content.call_args
    assert call.kwargs["model"] == "gemini-3-pro-image-preview"


def test_generate_image_auto_filename(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    monkeypatch.setattr(image_gen_tools, "_TMP_DIR", tmp_path)

    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = _mock_genai_response(
        _make_png_bytes()
    )

    with patch("google.genai.Client", return_value=fake_client):
        import asyncio
        result = asyncio.run(image_gen_tools.generate_image("cat"))

    assert result.endswith(".png")
    # Auto-generated filename has timestamp prefix
    assert "/" in result


def test_generate_image_invalid_resolution_falls_back(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    monkeypatch.setattr(image_gen_tools, "_TMP_DIR", tmp_path)

    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = _mock_genai_response(
        _make_png_bytes()
    )

    with patch("google.genai.Client", return_value=fake_client):
        import asyncio
        asyncio.run(
            image_gen_tools.generate_image("cat", resolution="16K")
        )

    # Should have fallen back to 2K
    call = fake_client.models.generate_content.call_args
    image_config = call.kwargs["config"].image_config
    assert image_config.image_size == "2K"


def test_generate_image_no_image_in_response(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    monkeypatch.setattr(image_gen_tools, "_TMP_DIR", tmp_path)

    # Response with only text parts, no inline_data
    text_part = MagicMock()
    text_part.text = "I can't do that"
    text_part.inline_data = None
    response = MagicMock()
    response.parts = [text_part]

    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = response

    with patch("google.genai.Client", return_value=fake_client):
        import asyncio
        result = asyncio.run(image_gen_tools.generate_image("cat"))

    assert "no image in response" in result
    assert "I can't do that" in result


def test_generate_image_api_exception_returns_error(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    monkeypatch.setattr(image_gen_tools, "_TMP_DIR", tmp_path)

    fake_client = MagicMock()
    fake_client.models.generate_content.side_effect = RuntimeError("quota hit")

    with patch("google.genai.Client", return_value=fake_client):
        import asyncio
        result = asyncio.run(image_gen_tools.generate_image("cat"))

    assert "generate_image failed" in result
    assert "quota hit" in result


def test_generate_image_b64_success(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    monkeypatch.setattr(image_gen_tools, "_TMP_DIR", tmp_path)

    png = _make_png_bytes()
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = _mock_genai_response(png)

    with patch("google.genai.Client", return_value=fake_client):
        import asyncio
        result = asyncio.run(image_gen_tools.generate_image_b64("cat"))

    # Should be valid base64 of PNG
    decoded = base64.b64decode(result)
    assert decoded.startswith(b"\x89PNG")


def test_generate_image_b64_propagates_error(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(image_gen_tools, "_TMP_DIR", tmp_path)

    import asyncio
    result = asyncio.run(image_gen_tools.generate_image_b64("cat"))
    assert "generate_image_b64 failed" in result
