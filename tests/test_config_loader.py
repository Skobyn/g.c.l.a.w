"""Tests for config loader."""

import pytest
from gclaw.config.loader import ConfigLoader


@pytest.fixture
def config_dir(tmp_path):
    soul_dir = tmp_path / "soul"
    soul_dir.mkdir()
    (soul_dir / "base.md").write_text(
        "You are a helpful assistant.\n"
        "Be concise and friendly.\n"
    )
    (soul_dir / "workspace.md").write_text(
        "For email, use a professional tone.\n"
    )
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "orchestrator.md").write_text(
        "You are the root orchestrator.\n"
        "Route tasks to the appropriate manager.\n"
    )
    (agents_dir / "workspace-mgr.md").write_text(
        "You manage Google Workspace tasks.\n"
    )
    return tmp_path


def test_load_soul_base(config_dir):
    loader = ConfigLoader(str(config_dir))
    soul = loader.load_soul("base")
    assert "helpful assistant" in soul


def test_load_soul_with_overlay(config_dir):
    loader = ConfigLoader(str(config_dir))
    soul = loader.load_soul("base", overlay="workspace")
    assert "helpful assistant" in soul
    assert "professional tone" in soul


def test_load_soul_missing_overlay_ignored(config_dir):
    loader = ConfigLoader(str(config_dir))
    soul = loader.load_soul("base", overlay="nonexistent")
    assert "helpful assistant" in soul


def test_load_agent_definition(config_dir):
    loader = ConfigLoader(str(config_dir))
    defn = loader.load_agent("orchestrator")
    assert "root orchestrator" in defn


def test_build_system_prompt(config_dir):
    loader = ConfigLoader(str(config_dir))
    prompt = loader.build_system_prompt(
        agent_name="orchestrator",
        soul_base="base",
    )
    assert "root orchestrator" in prompt
    assert "helpful assistant" in prompt


def test_build_system_prompt_with_overlay(config_dir):
    loader = ConfigLoader(str(config_dir))
    prompt = loader.build_system_prompt(
        agent_name="workspace-mgr",
        soul_base="base",
        soul_overlay="workspace",
    )
    assert "Google Workspace" in prompt
    assert "professional tone" in prompt
    assert "helpful assistant" in prompt


def test_build_system_prompt_with_memories(config_dir):
    loader = ConfigLoader(str(config_dir))
    memories = [
        "User prefers short responses.",
        "User's name is Sam.",
    ]
    prompt = loader.build_system_prompt(
        agent_name="orchestrator",
        soul_base="base",
        memories=memories,
    )
    assert "User prefers short responses." in prompt
    assert "User's name is Sam." in prompt


def test_missing_agent_raises(config_dir):
    loader = ConfigLoader(str(config_dir))
    with pytest.raises(FileNotFoundError):
        loader.load_agent("nonexistent")
