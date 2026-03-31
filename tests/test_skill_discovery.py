"""Tests for skill discovery — find skills by context."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from gclaw.models.skill import Skill, SkillTrigger, TriggerMode
from gclaw.skill.discovery import SkillDiscovery


@pytest.fixture
def skill_registry():
    return MagicMock()


@pytest.fixture
def discovery(skill_registry):
    return SkillDiscovery(registry=skill_registry)


def test_discover_by_context(discovery, skill_registry):
    skill_registry.list_for_agent.return_value = [
        Skill(
            name="email-drafter",
            description="Draft professional emails",
            trigger=SkillTrigger(
                mode=TriggerMode.AUTO,
                contexts=["composing email", "replying to thread"],
            ),
            agents_granted=["workspace-mgr"],
        ),
        Skill(
            name="meeting-scheduler",
            description="Schedule meetings",
            trigger=SkillTrigger(
                mode=TriggerMode.AUTO,
                contexts=["scheduling meeting", "calendar management"],
            ),
            agents_granted=["workspace-mgr"],
        ),
    ]

    matches = discovery.discover(
        agent_name="workspace-mgr",
        context="composing email to client",
    )

    assert len(matches) == 1
    assert matches[0].name == "email-drafter"


def test_discover_no_matches(discovery, skill_registry):
    skill_registry.list_for_agent.return_value = [
        Skill(
            name="email-drafter",
            description="Draft emails",
            trigger=SkillTrigger(
                mode=TriggerMode.AUTO,
                contexts=["composing email"],
            ),
            agents_granted=["workspace-mgr"],
        ),
    ]

    matches = discovery.discover(
        agent_name="workspace-mgr",
        context="writing code",
    )

    assert len(matches) == 0


def test_discover_by_description(discovery, skill_registry):
    """Fall back to description-based matching if no context match."""
    skill_registry.list_for_agent.return_value = [
        Skill(
            name="research-summarizer",
            description="Summarize research findings into concise reports",
            trigger=SkillTrigger(mode=TriggerMode.AUTO, contexts=[]),
            agents_granted=["research-mgr"],
        ),
    ]

    matches = discovery.discover(
        agent_name="research-mgr",
        context="summarize research",
    )

    assert len(matches) == 1
    assert matches[0].name == "research-summarizer"


def test_discover_manual_only_excluded(discovery, skill_registry):
    """Manual-only skills should not be auto-discovered."""
    skill_registry.list_for_agent.return_value = [
        Skill(
            name="custom-tool",
            description="A manual tool",
            trigger=SkillTrigger(
                mode=TriggerMode.MANUAL,
                contexts=["any context"],
                command="/custom",
            ),
            agents_granted=["workspace-mgr"],
        ),
    ]

    matches = discovery.discover(
        agent_name="workspace-mgr",
        context="any context here",
    )

    assert len(matches) == 0


def test_discover_by_command(discovery, skill_registry):
    """Direct command invocation lookup."""
    skill_registry.list_for_agent.return_value = [
        Skill(
            name="email-drafter",
            description="Draft emails",
            trigger=SkillTrigger(
                mode=TriggerMode.BOTH,
                contexts=["composing email"],
                command="/draft-email",
            ),
            agents_granted=["workspace-mgr"],
        ),
        Skill(
            name="other-skill",
            description="Other",
            trigger=SkillTrigger(
                mode=TriggerMode.MANUAL,
                command="/other",
            ),
            agents_granted=["workspace-mgr"],
        ),
    ]

    match = discovery.find_by_command(
        agent_name="workspace-mgr",
        command="/draft-email",
    )

    assert match is not None
    assert match.name == "email-drafter"


def test_find_by_command_not_found(discovery, skill_registry):
    skill_registry.list_for_agent.return_value = []

    match = discovery.find_by_command(
        agent_name="workspace-mgr",
        command="/nonexistent",
    )

    assert match is None
