"""Tests for GoogleChatAnnounceTransport."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from gclaw.cron.delivery import GoogleChatAnnounceTransport


async def test_send_no_channel_returns_false_and_skips_call():
    transport = GoogleChatAnnounceTransport()
    with patch(
        "gclaw.tools.comms_tools.post_chat_message",
        new=AsyncMock(return_value="Message sent"),
    ) as mock_post:
        ok = await transport.send(
            channel=None, to=None, account_id=None, message="hi"
        )
    assert ok is False
    mock_post.assert_not_called()


async def test_send_success_returns_true_and_calls_with_space_and_message():
    transport = GoogleChatAnnounceTransport()
    with patch(
        "gclaw.tools.comms_tools.post_chat_message",
        new=AsyncMock(return_value="Message sent to spaces/X: foo"),
    ) as mock_post:
        ok = await transport.send(
            channel="spaces/AAAA",
            to=None,
            account_id=None,
            message="hello there",
        )
    assert ok is True
    mock_post.assert_awaited_once_with("spaces/AAAA", "hello there")


async def test_send_comms_failure_string_returns_false():
    transport = GoogleChatAnnounceTransport()
    err = "Comms post chat message failed: gws: command not found"
    with patch(
        "gclaw.tools.comms_tools.post_chat_message",
        new=AsyncMock(return_value=err),
    ) as mock_post:
        ok = await transport.send(
            channel="spaces/AAAA",
            to=None,
            account_id=None,
            message="hello",
        )
    assert ok is False
    mock_post.assert_awaited_once()
