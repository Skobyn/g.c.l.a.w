"""Tests for read_user_profile / update_user_profile tools."""

from __future__ import annotations

import pytest

from gclaw.config.loader import ConfigLoader
from gclaw.tools import user_profile_tools


@pytest.fixture
def configured_loader(tmp_path):
    soul_dir = tmp_path / "soul"
    soul_dir.mkdir()
    (soul_dir / "base.md").write_text("You are helpful.\n")
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    loader = ConfigLoader(str(tmp_path))
    user_profile_tools.set_config_loader(loader)
    yield loader, tmp_path
    user_profile_tools.set_config_loader(None)


async def test_read_returns_blank_marker_when_missing(configured_loader):
    _, _ = configured_loader
    result = await user_profile_tools.read_user_profile()
    assert "blank" in result


async def test_update_writes_file_and_read_returns_it(configured_loader):
    _, root = configured_loader
    body = "# Identity\nName: Ada Lovelace.\n## Career\nEngineer.\n"
    out = await user_profile_tools.update_user_profile(body)
    assert "user.md updated" in out

    written = (root / "user.md").read_text()
    assert written == body

    read_back = await user_profile_tools.read_user_profile()
    assert "Ada Lovelace" in read_back


async def test_update_overwrites_previous_content(configured_loader):
    _, root = configured_loader
    (root / "user.md").write_text("old content")
    await user_profile_tools.update_user_profile("new content")
    assert (root / "user.md").read_text() == "new content"


async def test_read_without_loader_returns_error_string():
    user_profile_tools.set_config_loader(None)
    result = await user_profile_tools.read_user_profile()
    assert "failed" in result
