"""Tests for dev tool functions — GitHub and local file wrappers."""

from unittest.mock import AsyncMock, patch

import pytest

from gclaw.tools import dev_tools


@pytest.mark.asyncio
async def test_list_open_prs_formats_summary():
    mock_result = [
        {"number": 1, "title": "Fix bug", "author": {"login": "alice"}},
        {"number": 2, "title": "Add feature", "author": {"login": "bob"}},
    ]
    with patch(
        "gclaw.tools.dev_tools.run_gh",
        AsyncMock(return_value=mock_result),
    ):
        result = await dev_tools.list_open_prs()

    assert "#1" in result
    assert "Fix bug" in result
    assert "alice" in result
    assert "#2" in result


@pytest.mark.asyncio
async def test_list_open_prs_empty():
    with patch("gclaw.tools.dev_tools.run_gh", AsyncMock(return_value=[])):
        result = await dev_tools.list_open_prs()

    assert "No open PRs" in result


@pytest.mark.asyncio
async def test_get_pr_diff_returns_text():
    with patch(
        "gclaw.tools.dev_tools.run_gh",
        AsyncMock(return_value="diff --git a/file b/file\n+new line"),
    ):
        result = await dev_tools.get_pr_diff(pr_number=42)

    assert "diff --git" in result


@pytest.mark.asyncio
async def test_list_failing_workflows_formats_runs():
    mock_result = [
        {"name": "CI", "status": "completed", "conclusion": "failure", "displayTitle": "Fix bug"},
    ]
    with patch(
        "gclaw.tools.dev_tools.run_gh",
        AsyncMock(return_value=mock_result),
    ):
        result = await dev_tools.list_failing_workflows()

    assert "CI" in result
    assert "failure" in result


@pytest.mark.asyncio
async def test_list_failing_workflows_none():
    with patch(
        "gclaw.tools.dev_tools.run_gh",
        AsyncMock(return_value=[]),
    ):
        result = await dev_tools.list_failing_workflows()

    assert "No failing workflows" in result


@pytest.mark.asyncio
async def test_create_issue_returns_url():
    with patch(
        "gclaw.tools.dev_tools.run_gh",
        AsyncMock(return_value="https://github.com/org/repo/issues/99"),
    ):
        result = await dev_tools.create_issue(
            title="Bug report", body="Details here"
        )

    assert "https://github.com/org/repo/issues/99" in result


@pytest.mark.asyncio
async def test_get_current_diff_runs_git(monkeypatch):
    import subprocess

    def fake_run(*args, **kwargs):
        class R:
            stdout = "diff --git a/x b/x\n+line"
            returncode = 0
            stderr = ""
        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = await dev_tools.get_current_diff()
    assert "diff --git" in result


@pytest.mark.asyncio
async def test_read_local_file_returns_content(tmp_path):
    f = tmp_path / "example.py"
    f.write_text("print('hello')\n")

    result = await dev_tools.read_local_file(str(f))
    assert "print('hello')" in result


@pytest.mark.asyncio
async def test_read_local_file_missing_file_graceful(tmp_path):
    result = await dev_tools.read_local_file(str(tmp_path / "missing.txt"))
    assert "not found" in result.lower() or "failed" in result.lower()
