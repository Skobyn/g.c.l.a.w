"""Tests for per-agent user_knowledge resolution and user.md injection."""

from __future__ import annotations

import pytest

from gclaw.config.loader import ConfigLoader
from gclaw.models.agent_config import AgentOverride


@pytest.fixture
def config_dir(tmp_path):
    soul_dir = tmp_path / "soul"
    soul_dir.mkdir()
    (soul_dir / "base.md").write_text("You are a helpful assistant.\n")

    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "orchestrator.md").write_text(
        "---\n"
        "user_knowledge: true\n"
        "---\n"
        "You are the orchestrator.\n"
    )
    (agents_dir / "workspace-mgr.md").write_text(
        "You manage Google Workspace tasks.\n"
    )
    (agents_dir / "profile-mgr.md").write_text(
        "---\n"
        "user_knowledge: true\n"
        "---\n"
        "You own user.md.\n"
    )
    (agents_dir / "opt-in-mgr.md").write_text(
        "---\n"
        "user_knowledge: true\n"
        "---\n"
        "You opted in via frontmatter.\n"
    )
    (agents_dir / "explicit-off.md").write_text(
        "---\n"
        "user_knowledge: false\n"
        "---\n"
        "You opted out via frontmatter.\n"
    )
    return tmp_path


def _write_user_md(root, content: str) -> None:
    (root / "user.md").write_text(content)


def test_orchestrator_gets_user_profile_by_default(config_dir):
    _write_user_md(config_dir, "# Identity\nName: Ada.\n")
    loader = ConfigLoader(str(config_dir))
    prompt = loader.build_system_prompt(agent_name="orchestrator")
    assert "About the User" in prompt
    assert "Name: Ada." in prompt


def test_manager_does_not_get_user_profile_by_default(config_dir):
    _write_user_md(config_dir, "# Identity\nName: Ada.\n")
    loader = ConfigLoader(str(config_dir))
    prompt = loader.build_system_prompt(agent_name="workspace-mgr")
    assert "Name: Ada." not in prompt
    assert "About the User" not in prompt


def test_profile_mgr_gets_user_profile_by_default(config_dir):
    _write_user_md(config_dir, "# Identity\nName: Ada.\n")
    loader = ConfigLoader(str(config_dir))
    prompt = loader.build_system_prompt(agent_name="profile-mgr")
    assert "About the User" in prompt
    assert "Name: Ada." in prompt


def test_frontmatter_can_opt_in_a_manager(config_dir):
    _write_user_md(config_dir, "# Identity\nName: Ada.\n")
    loader = ConfigLoader(str(config_dir))
    prompt = loader.build_system_prompt(agent_name="opt-in-mgr")
    assert "Name: Ada." in prompt


def test_frontmatter_can_explicitly_opt_out_a_default_on_agent(config_dir):
    _write_user_md(config_dir, "# Identity\nName: Ada.\n")
    # Rewrite orchestrator.md with user_knowledge: false
    (config_dir / "agents" / "orchestrator.md").write_text(
        "---\nuser_knowledge: false\n---\nOrchestrator body.\n"
    )
    loader = ConfigLoader(str(config_dir))
    prompt = loader.build_system_prompt(agent_name="orchestrator")
    assert "About the User" not in prompt


def test_override_beats_frontmatter_off_to_on(config_dir):
    _write_user_md(config_dir, "# Identity\nName: Ada.\n")
    override = AgentOverride(agent_name="workspace-mgr", user_knowledge=True)
    loader = ConfigLoader(
        str(config_dir),
        override_provider=lambda name: override if name == "workspace-mgr" else None,
    )
    prompt = loader.build_system_prompt(agent_name="workspace-mgr")
    assert "Name: Ada." in prompt


def test_override_beats_frontmatter_on_to_off(config_dir):
    _write_user_md(config_dir, "# Identity\nName: Ada.\n")
    override = AgentOverride(agent_name="orchestrator", user_knowledge=False)
    loader = ConfigLoader(
        str(config_dir),
        override_provider=lambda name: override if name == "orchestrator" else None,
    )
    prompt = loader.build_system_prompt(agent_name="orchestrator")
    assert "About the User" not in prompt


def test_blank_user_md_yields_onboarding_hint_for_opted_in_agent(config_dir):
    # No user.md created.
    loader = ConfigLoader(str(config_dir))
    prompt = loader.build_system_prompt(agent_name="orchestrator")
    assert "About the User" in prompt
    assert "profile is blank" in prompt


def test_blank_user_md_no_section_for_opted_out_agent(config_dir):
    loader = ConfigLoader(str(config_dir))
    prompt = loader.build_system_prompt(agent_name="workspace-mgr")
    assert "About the User" not in prompt


def test_resolve_user_knowledge_override_none_falls_through(config_dir):
    """An override with user_knowledge=None must not force the value;
    resolution should fall through to frontmatter / per-agent default."""
    override = AgentOverride(agent_name="workspace-mgr", user_knowledge=None)
    loader = ConfigLoader(
        str(config_dir),
        override_provider=lambda name: override if name == "workspace-mgr" else None,
    )
    assert loader.resolve_user_knowledge("workspace-mgr") is False
    assert loader.resolve_user_knowledge("orchestrator") is True


def test_user_profile_is_blank_helper(config_dir, tmp_path):
    loader = ConfigLoader(str(config_dir))
    assert loader.user_profile_is_blank() is True
    _write_user_md(config_dir, "# Identity\nName: Ada.\n")
    assert loader.user_profile_is_blank() is False
