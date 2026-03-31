"""Tests for skill registry."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from gclaw.models.skill import Skill, SkillSource, SkillTrigger, TriggerMode
from gclaw.skill.registry import SkillRegistry


@pytest.fixture
def skill_repo():
    return MagicMock()


@pytest.fixture
def registry(skill_repo):
    return SkillRegistry(skill_repo=skill_repo)


def test_register_skill(registry, skill_repo):
    skill = Skill(
        name="email-drafter",
        description="Draft emails",
        agents_granted=["workspace-mgr"],
    )
    skill_repo.save.side_effect = lambda s: s

    result = registry.register(skill)

    assert result.name == "email-drafter"
    skill_repo.save.assert_called_once()


def test_get_skill(registry, skill_repo):
    skill_repo.get.return_value = Skill(
        name="email-drafter",
        description="Draft emails",
    )

    result = registry.get("email-drafter")

    assert result is not None
    assert result.name == "email-drafter"


def test_get_nonexistent_skill(registry, skill_repo):
    skill_repo.get.return_value = None

    result = registry.get("nonexistent")

    assert result is None


def test_list_all(registry, skill_repo):
    skill_repo.list_all.return_value = [
        Skill(name="skill-1", description="First"),
        Skill(name="skill-2", description="Second"),
    ]

    skills = registry.list_all()

    assert len(skills) == 2


def test_list_for_agent(registry, skill_repo):
    skill_repo.list_all.return_value = [
        Skill(name="email-drafter", description="Draft emails",
              agents_granted=["workspace-mgr"]),
        Skill(name="code-review", description="Review code",
              agents_granted=["dev-mgr"]),
        Skill(name="research", description="Web research",
              agents_granted=["workspace-mgr", "research-mgr"]),
    ]

    skills = registry.list_for_agent("workspace-mgr")

    assert len(skills) == 2
    names = [s.name for s in skills]
    assert "email-drafter" in names
    assert "research" in names
    assert "code-review" not in names


def test_unregister_skill(registry, skill_repo):
    registry.unregister("email-drafter")
    skill_repo.delete.assert_called_once_with("email-drafter")


def test_load_builtins(registry, skill_repo, tmp_path):
    """Test loading built-in skills from a directory."""
    # Create a skill directory
    skill_dir = tmp_path / "skills" / "test-skill"
    skill_dir.mkdir(parents=True)
    skill_json = skill_dir / "skill.json"
    skill_json.write_text(
        '{"name": "test-skill", "description": "A test skill", '
        '"version": "1.0.0", "trigger": {"mode": "manual", "contexts": [], "command": "/test"}, '
        '"config": {}, "tools_required": [], "agents_granted": ["workspace-mgr"], '
        '"source": "builtin"}'
    )

    skill_repo.save.side_effect = lambda s: s
    skill_repo.get.return_value = None

    loaded = registry.load_builtins(str(tmp_path / "skills"))

    assert len(loaded) == 1
    assert loaded[0].name == "test-skill"
    skill_repo.save.assert_called_once()
