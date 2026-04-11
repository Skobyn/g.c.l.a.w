"""Tests for research tool functions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gclaw.tools import research_tools


@pytest.mark.asyncio
async def test_web_search_stub_returns_placeholder():
    result = await research_tools.web_search("test query")
    assert "test query" in result
    assert "stub" in result.lower() or "not yet" in result.lower() or "placeholder" in result.lower()


@pytest.mark.asyncio
async def test_fetch_url_returns_text():
    mock_response = MagicMock()
    mock_response.text = "<html><body>Hello</body></html>"
    mock_response.status_code = 200

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_class.return_value.__aenter__.return_value = mock_client
        result = await research_tools.fetch_url("https://example.com")

    assert "Hello" in result


@pytest.mark.asyncio
async def test_fetch_url_handles_failure():
    import httpx

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))
        mock_client_class.return_value.__aenter__.return_value = mock_client
        result = await research_tools.fetch_url("https://example.com")

    assert "fail" in result.lower() or "error" in result.lower()
