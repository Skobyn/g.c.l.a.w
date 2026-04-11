"""Tests for workspace tool functions — Gmail, Calendar, Drive, Docs wrappers."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from gclaw.tools import workspace_tools


@pytest.mark.asyncio
async def test_list_unread_email_empty_inbox():
    with patch(
        "gclaw.tools.workspace_tools.run_gws",
        AsyncMock(return_value={"messages": []}),
    ):
        result = await workspace_tools.list_unread_email(max_results=5)

    assert result == "No unread email."


@pytest.mark.asyncio
async def test_list_unread_email_formats_summary():
    first_call_result = {"messages": [{"id": "abc"}, {"id": "def"}]}
    detail_1 = {
        "payload": {
            "headers": [
                {"name": "From", "value": "alice@example.com"},
                {"name": "Subject", "value": "Hello"},
            ]
        }
    }
    detail_2 = {
        "payload": {
            "headers": [
                {"name": "From", "value": "bob@example.com"},
                {"name": "Subject", "value": "Meeting"},
            ]
        }
    }

    with patch(
        "gclaw.tools.workspace_tools.run_gws",
        AsyncMock(side_effect=[first_call_result, detail_1, detail_2]),
    ) as mock_run:
        result = await workspace_tools.list_unread_email(max_results=2)

    assert "alice@example.com" in result
    assert "Hello" in result
    assert "bob@example.com" in result
    assert "Meeting" in result
    assert mock_run.call_count == 3


@pytest.mark.asyncio
async def test_list_calendar_events_today_formats_events():
    mock_result = {
        "items": [
            {
                "summary": "Standup",
                "start": {"dateTime": "2026-04-10T09:00:00Z"},
                "end": {"dateTime": "2026-04-10T09:30:00Z"},
            },
            {
                "summary": "Lunch with Pat",
                "start": {"dateTime": "2026-04-10T12:00:00Z"},
                "end": {"dateTime": "2026-04-10T13:00:00Z"},
            },
        ]
    }
    with patch(
        "gclaw.tools.workspace_tools.run_gws",
        AsyncMock(return_value=mock_result),
    ):
        result = await workspace_tools.list_calendar_events_today()

    assert "Standup" in result
    assert "Lunch with Pat" in result


@pytest.mark.asyncio
async def test_list_calendar_events_today_no_events():
    with patch(
        "gclaw.tools.workspace_tools.run_gws",
        AsyncMock(return_value={"items": []}),
    ):
        result = await workspace_tools.list_calendar_events_today()

    assert "No events" in result


@pytest.mark.asyncio
async def test_send_email_calls_gws_with_payload():
    with patch(
        "gclaw.tools.workspace_tools.run_gws",
        AsyncMock(return_value={"id": "sent-123"}),
    ) as mock_run:
        result = await workspace_tools.send_email(
            to="alice@example.com",
            subject="Hello",
            body="Hi Alice",
        )

    assert "sent" in result.lower() or "sent-123" in result
    mock_run.assert_called_once()
    args = mock_run.call_args.args
    assert "gmail" in args


@pytest.mark.asyncio
async def test_list_drive_files_formats_names():
    mock_result = {
        "files": [
            {"id": "1", "name": "Budget.xlsx", "mimeType": "application/vnd.ms-excel"},
            {"id": "2", "name": "Plan.doc", "mimeType": "application/msword"},
        ]
    }
    with patch(
        "gclaw.tools.workspace_tools.run_gws",
        AsyncMock(return_value=mock_result),
    ):
        result = await workspace_tools.list_drive_files(max_results=10)

    assert "Budget.xlsx" in result
    assert "Plan.doc" in result


@pytest.mark.asyncio
async def test_workspace_tools_handle_gws_error_gracefully():
    from gclaw.tools.gws import GwsError

    with patch(
        "gclaw.tools.workspace_tools.run_gws",
        AsyncMock(side_effect=GwsError("auth failed")),
    ):
        result = await workspace_tools.list_unread_email()

    assert "error" in result.lower() or "not configured" in result.lower() or "failed" in result.lower()
