"""Tests for comms tool functions — Google Chat via gws."""

from unittest.mock import AsyncMock, patch

import pytest

from gclaw.tools import comms_tools


@pytest.mark.asyncio
async def test_list_chat_spaces_formats():
    mock_result = {
        "spaces": [
            {"name": "spaces/abc", "displayName": "Team"},
            {"name": "spaces/def", "displayName": "Ops"},
        ]
    }
    with patch(
        "gclaw.tools.comms_tools.run_gws",
        AsyncMock(return_value=mock_result),
    ):
        result = await comms_tools.list_chat_spaces()

    assert "Team" in result
    assert "Ops" in result


@pytest.mark.asyncio
async def test_list_chat_spaces_empty():
    with patch(
        "gclaw.tools.comms_tools.run_gws",
        AsyncMock(return_value={"spaces": []}),
    ):
        result = await comms_tools.list_chat_spaces()

    assert "No chat spaces" in result


@pytest.mark.asyncio
async def test_post_chat_message_returns_confirmation():
    with patch(
        "gclaw.tools.comms_tools.run_gws",
        AsyncMock(return_value={"name": "spaces/abc/messages/123"}),
    ):
        result = await comms_tools.post_chat_message(
            space_name="spaces/abc", text="Hello team"
        )

    assert "spaces/abc" in result or "sent" in result.lower()
