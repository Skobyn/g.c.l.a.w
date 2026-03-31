"""Tests for skill loader — reads skill files and builds prompt sections."""

from __future__ import annotations

import pytest

from gclaw.models.skill import Skill, SkillTrigger, TriggerMode
from gclaw.skill.loader import SkillLoader


@pytest.fixture
def skill_dir(tmp_path):
    """Create a skill directory with instructions and examples."""
    skill_path = tmp_path / "skills" / "email-drafter"
    skill_path.mkdir(parents=True)

    (skill_path / "instructions.md").write_text(
        "# Email Drafter\n\n"
        "When drafting an email:\n"
        "1. Match the user's tone and formality level\n"
        "2. Keep it concise\n"
        "3. Always include a greeting and sign-off\n"
    )
    (skill_path / "examples.md").write_text(
        "# Examples\n\n"
        "## Professional email\n"
        "Subject: Q2 Roadmap Update\n"
        "Hi Sarah, ...\n"
    )
    return tmp_path


@pytest.fixture
def loader():
    return SkillLoader()


def test_load_instructions(loader, skill_dir):
    skill = Skill(
        name="email-drafter",
        description="Draft emails",
        instructions_path=str(skill_dir / "skills" / "email-drafter" / "instructions.md"),
    )

    instructions = loader.load_instructions(skill)

    assert "Email Drafter" in instructions
    assert "Match the user's tone" in instructions


def test_load_examples(loader, skill_dir):
    skill = Skill(
        name="email-drafter",
        description="Draft emails",
        examples_path=str(skill_dir / "skills" / "email-drafter" / "examples.md"),
    )

    examples = loader.load_examples(skill)

    assert "Professional email" in examples
    assert "Q2 Roadmap Update" in examples


def test_load_missing_instructions(loader):
    skill = Skill(
        name="email-drafter",
        description="Draft emails",
        instructions_path="/nonexistent/path/instructions.md",
    )

    instructions = loader.load_instructions(skill)

    assert instructions == ""


def test_load_no_path(loader):
    skill = Skill(
        name="email-drafter",
        description="Draft emails",
    )

    assert loader.load_instructions(skill) == ""
    assert loader.load_examples(skill) == ""


def test_build_skill_prompt_section(loader, skill_dir):
    skill = Skill(
        name="email-drafter",
        description="Draft professional emails matching user's tone",
        config={"formality": "professional"},
        instructions_path=str(skill_dir / "skills" / "email-drafter" / "instructions.md"),
        examples_path=str(skill_dir / "skills" / "email-drafter" / "examples.md"),
    )

    section = loader.build_prompt_section(skill)

    assert "## Skill: email-drafter" in section
    assert "Draft professional emails" in section
    assert "Email Drafter" in section
    assert "Professional email" in section
    assert "formality" in section


def test_build_prompt_section_minimal(loader):
    skill = Skill(
        name="test-skill",
        description="A minimal skill",
    )

    section = loader.build_prompt_section(skill)

    assert "## Skill: test-skill" in section
    assert "A minimal skill" in section


def test_build_multi_skill_prompt(loader, skill_dir):
    skills = [
        Skill(
            name="email-drafter",
            description="Draft emails",
            instructions_path=str(skill_dir / "skills" / "email-drafter" / "instructions.md"),
        ),
        Skill(
            name="research",
            description="Web research",
        ),
    ]

    prompt = loader.build_skills_prompt(skills)

    assert "# Available Skills" in prompt
    assert "email-drafter" in prompt
    assert "research" in prompt
