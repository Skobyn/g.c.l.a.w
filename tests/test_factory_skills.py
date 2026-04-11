"""Tests for AgentFactory skill injection via SkillRegistry."""

from __future__ import annotations

import pytest

from gclaw.agents.factory import AgentFactory
from gclaw.config.loader import ConfigLoader
from gclaw.models.skill import Skill, SkillTrigger, TriggerMode
from gclaw.skill.in_memory_repo import InMemorySkillRepo
from gclaw.skill.loader import SkillLoader
from gclaw.skill.registry import SkillRegistry


@pytest.fixture
def config_dir(tmp_path):
    soul_dir = tmp_path / "soul"
    soul_dir.mkdir()
    (soul_dir / "base.md").write_text("Base personality.\n")
    (soul_dir / "comms.md").write_text("Comms overlay.\n")
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "comms-mgr.md").write_text("Comms manager role.\n")
    (agents_dir / "dev-mgr.md").write_text("Dev manager role.\n")
    (agents_dir / "orchestrator.md").write_text("Orchestrator role.\n")
    return tmp_path


@pytest.fixture
def skills_dir(tmp_path):
    """Create a skills/ directory with a minimal skill.json + instructions.md."""
    skills = tmp_path / "skills"
    (skills / "demo-drafter").mkdir(parents=True)
    (skills / "demo-drafter" / "skill.json").write_text(
        '{"name":"demo-drafter","description":"Draft demo content",'
        '"version":"1.0.0","trigger":{"mode":"both","contexts":["demo"]},'
        '"config":{},"tools_required":[],'
        '"agents_granted":["comms-mgr"],"source":"builtin"}'
    )
    (skills / "demo-drafter" / "instructions.md").write_text(
        "Always sign off with 'Regards, GClaw'."
    )

    (skills / "demo-reviewer").mkdir()
    (skills / "demo-reviewer" / "skill.json").write_text(
        '{"name":"demo-reviewer","description":"Score diffs",'
        '"version":"1.0.0","trigger":{"mode":"both","contexts":["review"]},'
        '"config":{},"tools_required":[],'
        '"agents_granted":["dev-mgr"],"source":"builtin"}'
    )
    (skills / "demo-reviewer" / "instructions.md").write_text(
        "Score across security, correctness, tests."
    )
    return str(skills)


@pytest.fixture
def registry(skills_dir):
    reg = SkillRegistry(skill_repo=InMemorySkillRepo())
    reg.load_builtins(skills_dir)
    return reg


def test_registry_loads_builtins(registry):
    skills = registry.list_all()
    names = {s.name for s in skills}
    assert names == {"demo-drafter", "demo-reviewer"}


def test_registry_filters_by_agent(registry):
    comms = registry.list_for_agent("comms-mgr")
    assert [s.name for s in comms] == ["demo-drafter"]

    dev = registry.list_for_agent("dev-mgr")
    assert [s.name for s in dev] == ["demo-reviewer"]

    orch = registry.list_for_agent("orchestrator")
    assert orch == []


def test_factory_injects_granted_skill_into_prompt(config_dir, registry):
    skill_loader = SkillLoader()
    loader = ConfigLoader(str(config_dir), skill_loader=skill_loader)
    factory = AgentFactory(
        loader=loader,
        default_model="gemini-2.5-flash",
        skill_registry=registry,
    )
    agent = factory.build(agent_name="comms-mgr", soul_overlay="comms")

    assert "Skill: demo-drafter" in agent.instruction
    assert "Regards, GClaw" in agent.instruction
    # Other agents' skills must not leak in.
    assert "demo-reviewer" not in agent.instruction


def test_factory_no_skill_registry_is_no_op(config_dir):
    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(
        loader=loader,
        default_model="gemini-2.5-flash",
    )
    agent = factory.build(agent_name="comms-mgr", soul_overlay="comms")
    assert "Skill:" not in agent.instruction


def test_factory_explicit_skills_override_registry(config_dir, registry):
    skill_loader = SkillLoader()
    loader = ConfigLoader(str(config_dir), skill_loader=skill_loader)
    factory = AgentFactory(
        loader=loader,
        default_model="gemini-2.5-flash",
        skill_registry=registry,
    )
    # Explicit empty list should suppress any skills (not fall back to registry).
    agent = factory.build(
        agent_name="comms-mgr", soul_overlay="comms", skills=[]
    )
    assert "Skill:" not in agent.instruction


def test_real_code_review_skill_is_granted_to_dev_mgr():
    """Smoke test against the real on-disk code-review skill."""
    import os
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    skills_path = os.path.join(repo_root, "skills")

    reg = SkillRegistry(skill_repo=InMemorySkillRepo())
    reg.load_builtins(skills_path)
    dev_skills = {s.name for s in reg.list_for_agent("dev-mgr")}
    assert "code-review" in dev_skills
