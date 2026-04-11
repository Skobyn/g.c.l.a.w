"""Tests for the gws subprocess helper."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gclaw.tools.gws import GwsError, run_gws


@pytest.mark.asyncio
async def test_run_gws_parses_json_stdout():
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(
        return_value=(b'{"files": [{"name": "doc.txt"}]}', b"")
    )

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        result = await run_gws("drive", "files.list")

    assert result == {"files": [{"name": "doc.txt"}]}


@pytest.mark.asyncio
async def test_run_gws_passes_args_verbatim():
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"{}", b""))

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)) as spawn:
        await run_gws("gmail", "users.messages.list", "--params", '{"userId":"me"}')

    call_args = spawn.call_args.args
    assert call_args[0] == "gws"
    assert call_args[1:] == (
        "gmail", "users.messages.list", "--params", '{"userId":"me"}',
    )


@pytest.mark.asyncio
async def test_run_gws_raises_on_nonzero_exit():
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(return_value=(b"", b"auth error"))

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        with pytest.raises(GwsError, match="auth error"):
            await run_gws("drive", "files.list")


@pytest.mark.asyncio
async def test_run_gws_raises_on_invalid_json():
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"not json", b""))

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        with pytest.raises(GwsError, match="non-JSON"):
            await run_gws("drive", "files.list")


@pytest.mark.asyncio
async def test_run_gws_empty_stdout_returns_empty_dict():
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        result = await run_gws("drive", "files.list")

    assert result == {}


@pytest.mark.asyncio
async def test_run_gws_timeout_kills_process():
    import asyncio as asyncio_module

    mock_proc = MagicMock()
    mock_proc.returncode = None
    mock_proc.communicate = AsyncMock(side_effect=asyncio_module.TimeoutError)
    mock_proc.kill = MagicMock()

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        with pytest.raises(GwsError, match="timed out"):
            await run_gws("drive", "files.list", timeout=0.1)

    mock_proc.kill.assert_called_once()
