"""Factory applies AgentOverride filters for tools/subagents/skills."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from gclaw.agents.factory import AgentFactory
from gclaw.config.loader import ConfigLoader
from gclaw.models.agent_config import (
    AgentOverride,
    AgentSubagentsSpec,
    AgentToolsSpec,
)
from gclaw.models.skill import Skill


def _tool(name):
    def f(*a, **k):  # pragma: no cover - body unused
        return None
    f.__name__ = name
    return f


@pytest.fixture
def loader(tmp_path: Path) -> ConfigLoader:
    (tmp_path / "agents").mkdir()
    (tmp_path / "soul").mkdir()
    (tmp_path / "soul" / "base.md").write_text("base soul")
    (tmp_path / "agents" / "test-agent.md").write_text("You are test.")
    return ConfigLoader(str(tmp_path))


class _StubSvc:
    def __init__(self, override):
        self._o = override

    def get_override(self, name):
        return self._o if name == "test-agent" else None


def test_apply_override_tools_deny(loader):
    svc = _StubSvc(AgentOverride(
        agent_name="test-agent",
        tools=AgentToolsSpec(deny=["bad_tool"]),
    ))
    f = AgentFactory(loader=loader, agent_config_service=svc)
    t1 = _tool("bad_tool")
    t2 = _tool("good_tool")
    tools, _, _ = f._apply_override("test-agent", [t1, t2], None, None)
    assert tools == [t2]


def test_apply_override_tools_allow(loader):
    svc = _StubSvc(AgentOverride(
        agent_name="test-agent",
        tools=AgentToolsSpec(allow=["only_this"]),
    ))
    f = AgentFactory(loader=loader, agent_config_service=svc)
    t1 = _tool("only_this")
    t2 = _tool("other")
    tools, _, _ = f._apply_override("test-agent", [t1, t2], None, None)
    assert tools == [t1]


def test_apply_override_subagents_allowlist(loader):
    svc = _StubSvc(AgentOverride(
        agent_name="test-agent",
        subagents=AgentSubagentsSpec(allow=["dev-mgr"]),
    ))
    f = AgentFactory(loader=loader, agent_config_service=svc)
    a1 = MagicMock()
    a1.name = "dev_mgr"
    a2 = MagicMock()
    a2.name = "home_mgr"
    _, subs, _ = f._apply_override("test-agent", None, [a1, a2], None)
    assert subs == [a1]


def test_apply_override_subagents_wildcard(loader):
    svc = _StubSvc(AgentOverride(
        agent_name="test-agent",
        subagents=AgentSubagentsSpec(allow=["*"]),
    ))
    f = AgentFactory(loader=loader, agent_config_service=svc)
    a1 = MagicMock()
    a1.name = "x"
    _, subs, _ = f._apply_override("test-agent", None, [a1], None)
    assert subs == [a1]


def test_apply_override_skills_allowlist(loader):
    svc = _StubSvc(AgentOverride(
        agent_name="test-agent",
        skills=["keep-me"],
    ))
    f = AgentFactory(loader=loader, agent_config_service=svc)
    s1 = Skill(name="keep-me", description="")
    s2 = Skill(name="drop", description="")
    _, _, skills = f._apply_override("test-agent", None, None, [s1, s2])
    assert [s.name for s in skills] == ["keep-me"]


def test_no_override_no_filtering(loader):
    svc = _StubSvc(None)
    f = AgentFactory(loader=loader, agent_config_service=svc)
    t1 = _tool("a")
    tools, subs, skills = f._apply_override(
        "test-agent", [t1], None, [Skill(name="x", description="")]
    )
    assert tools == [t1]
    assert subs is None
    assert [s.name for s in skills] == ["x"]
