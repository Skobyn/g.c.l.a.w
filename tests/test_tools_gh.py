"""Tests for the gh subprocess helper."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gclaw.tools.gh import GhError, run_gh


@pytest.mark.asyncio
async def test_run_gh_parses_json_stdout():
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b'[{"number": 1}]', b""))

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        result = await run_gh("pr", "list", "--json", "number")

    assert result == [{"number": 1}]


@pytest.mark.asyncio
async def test_run_gh_passes_args_verbatim():
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"{}", b""))

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)) as spawn:
        await run_gh("pr", "view", "123", "--json", "title,body")

    call_args = spawn.call_args.args
    assert call_args[0] == "gh"
    assert call_args[1:] == ("pr", "view", "123", "--json", "title,body")


@pytest.mark.asyncio
async def test_run_gh_raises_on_nonzero_exit():
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(return_value=(b"", b"not authenticated"))

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        with pytest.raises(GhError, match="not authenticated"):
            await run_gh("pr", "list")


@pytest.mark.asyncio
async def test_run_gh_raises_on_invalid_json_when_parse_json_true():
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"not json", b""))

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        with pytest.raises(GhError, match="non-JSON"):
            await run_gh("pr", "list", parse_json=True)


@pytest.mark.asyncio
async def test_run_gh_returns_raw_string_when_parse_json_false():
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"raw text output", b""))

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        result = await run_gh("pr", "diff", "123", parse_json=False)

    assert result == "raw text output"
