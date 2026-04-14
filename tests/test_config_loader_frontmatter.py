"""Tests for ConfigLoader YAML frontmatter handling."""

import pytest

from gclaw.config.loader import ConfigLoader
from gclaw.heartbeat.config import HeartbeatConfig


@pytest.fixture
def config_dir(tmp_path):
    soul_dir = tmp_path / "soul"
    soul_dir.mkdir()
    (soul_dir / "base.md").write_text("You are a helpful assistant.\n")
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "with-fm.md").write_text(
        "---\n"
        "heartbeat:\n"
        "  enabled: true\n"
        "  every: 15m\n"
        "  isolated_session: true\n"
        "  light_context: true\n"
        "  ack_max_chars: 60\n"
        "  active_hours:\n"
        "    start: \"07:00\"\n"
        "    end: \"23:00\"\n"
        "    timezone: America/Los_Angeles\n"
        "---\n"
        "You are the agent body.\n"
    )
    (agents_dir / "no-fm.md").write_text(
        "You are a plain agent without frontmatter.\n"
    )
    (agents_dir / "fm-no-heartbeat.md").write_text(
        "---\n"
        "other_key: value\n"
        "---\n"
        "Body here.\n"
    )
    (agents_dir / "empty-fm.md").write_text(
        "---\n---\nBody only.\n"
    )
    (agents_dir / "bad-heartbeat.md").write_text(
        "---\nheartbeat: not-a-mapping\n---\nbody\n"
    )
    return tmp_path


def test_load_agent_heartbeat_config_parses(config_dir):
    loader = ConfigLoader(str(config_dir))
    hb = loader.load_agent_heartbeat_config("with-fm")
    assert isinstance(hb, HeartbeatConfig)
    assert hb.enabled is True
    assert hb.every == "15m"
    assert hb.isolated_session is True
    assert hb.light_context is True
    assert hb.ack_max_chars == 60
    assert hb.active_hours is not None
    assert hb.active_hours.start == "07:00"
    assert hb.active_hours.end == "23:00"
    assert hb.active_hours.timezone == "America/Los_Angeles"


def test_load_agent_heartbeat_config_none_when_no_frontmatter(config_dir):
    loader = ConfigLoader(str(config_dir))
    assert loader.load_agent_heartbeat_config("no-fm") is None


def test_load_agent_heartbeat_config_none_when_key_absent(config_dir):
    loader = ConfigLoader(str(config_dir))
    assert loader.load_agent_heartbeat_config("fm-no-heartbeat") is None


def test_load_agent_heartbeat_config_none_when_empty_fm(config_dir):
    loader = ConfigLoader(str(config_dir))
    assert loader.load_agent_heartbeat_config("empty-fm") is None


def test_load_agent_heartbeat_config_bad_shape_raises(config_dir):
    loader = ConfigLoader(str(config_dir))
    with pytest.raises(ValueError):
        loader.load_agent_heartbeat_config("bad-heartbeat")


def test_load_agent_strips_frontmatter(config_dir):
    loader = ConfigLoader(str(config_dir))
    body = loader.load_agent("with-fm")
    assert "heartbeat" not in body
    assert "---" not in body
    assert "You are the agent body." in body


def test_load_agent_without_frontmatter_unchanged(config_dir):
    loader = ConfigLoader(str(config_dir))
    body = loader.load_agent("no-fm")
    assert body.startswith("You are a plain agent")


def test_build_system_prompt_strips_frontmatter(config_dir):
    loader = ConfigLoader(str(config_dir))
    prompt = loader.build_system_prompt(
        agent_name="with-fm",
        soul_base="base",
    )
    assert "You are the agent body." in prompt
    # frontmatter keys/delimiter must not leak into the prompt body section
    # (the "---" between sections is allowed, but "heartbeat:" and "every:"
    # should not appear).
    assert "heartbeat:" not in prompt
    assert "enabled: true" not in prompt
    assert "You are a helpful assistant." in prompt


def test_build_system_prompt_no_frontmatter_still_works(config_dir):
    loader = ConfigLoader(str(config_dir))
    prompt = loader.build_system_prompt(
        agent_name="no-fm",
        soul_base="base",
    )
    assert "plain agent" in prompt
    assert "helpful assistant" in prompt
