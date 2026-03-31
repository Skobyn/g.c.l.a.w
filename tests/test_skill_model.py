"""Tests for skill model."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from gclaw.models.skill import (
    Skill,
    SkillTrigger,
    TriggerMode,
    SkillSource,
)


def test_create_minimal_skill():
    skill = Skill(
        name="email-drafter",
        description="Draft professional emails matching user's tone",
    )
    assert skill.name == "email-drafter"
    assert skill.description == "Draft professional emails matching user's tone"
    assert skill.source == SkillSource.BUILTIN
    assert skill.tools_required == []
    assert skill.agents_granted == []


def test_create_full_skill():
    skill = Skill(
        name="email-drafter",
        description="Draft professional emails",
        version="1.2.0",
        trigger=SkillTrigger(
            mode=TriggerMode.BOTH,
            contexts=["composing email", "replying to thread"],
            command="/draft-email",
        ),
        config={"formality": "professional", "max_length": 500},
        tools_required=["gmail", "contacts"],
        agents_granted=["workspace-mgr", "comms-mgr"],
        source=SkillSource.BUILTIN,
        instructions_path="skills/email-drafter/instructions.md",
        examples_path="skills/email-drafter/examples.md",
    )
    assert skill.trigger.mode == TriggerMode.BOTH
    assert len(skill.trigger.contexts) == 2
    assert skill.trigger.command == "/draft-email"
    assert skill.config["formality"] == "professional"
    assert "gmail" in skill.tools_required
    assert "workspace-mgr" in skill.agents_granted


def test_skill_trigger_auto_mode():
    trigger = SkillTrigger(
        mode=TriggerMode.AUTO,
        contexts=["scheduling meeting"],
    )
    assert trigger.mode == TriggerMode.AUTO
    assert trigger.command is None


def test_skill_to_firestore_dict():
    skill = Skill(
        name="test-skill",
        description="A test skill",
        tools_required=["gmail"],
    )
    d = skill.to_firestore_dict()
    assert d["name"] == "test-skill"
    assert d["tools_required"] == ["gmail"]


def test_skill_from_firestore_dict():
    d = {
        "name": "email-drafter",
        "description": "Draft emails",
        "version": "1.0.0",
        "trigger": {
            "mode": "auto",
            "contexts": ["composing email"],
            "command": None,
        },
        "config": {},
        "tools_required": ["gmail"],
        "agents_granted": ["workspace-mgr"],
        "source": "builtin",
        "instructions_path": None,
        "examples_path": None,
    }
    skill = Skill.from_firestore_dict(d)
    assert skill.name == "email-drafter"
    assert skill.trigger.mode == TriggerMode.AUTO
    assert skill.source == SkillSource.BUILTIN


def test_skill_is_granted_to():
    skill = Skill(
        name="test",
        description="Test",
        agents_granted=["workspace-mgr", "comms-mgr"],
    )
    assert skill.is_granted_to("workspace-mgr") is True
    assert skill.is_granted_to("dev-mgr") is False


def test_skill_matches_context():
    skill = Skill(
        name="test",
        description="Test",
        trigger=SkillTrigger(
            mode=TriggerMode.AUTO,
            contexts=["composing email", "replying to thread"],
        ),
    )
    assert skill.matches_context("composing email") is True
    assert skill.matches_context("scheduling meeting") is False
    # Partial match
    assert skill.matches_context("composing") is True
