"""Tests for AgentRunnerRegistry."""

from __future__ import annotations

from unittest.mock import MagicMock

from gclaw.dispatch.runner_registry import AgentRunnerRegistry


def test_get_defaults_when_name_is_none():
    built = {}

    def builder(name: str):
        built[name] = MagicMock(name=f"runner:{name}")
        return built[name]

    reg = AgentRunnerRegistry(default_agent="orchestrator", builder=builder)
    runner = reg.get(None)

    assert runner is built["orchestrator"]
    assert reg.default_agent() == "orchestrator"


def test_get_lazy_builds_on_first_access_and_caches():
    call_count = {"n": 0}

    def builder(name: str):
        call_count["n"] += 1
        m = MagicMock()
        m.agent_name = name
        return m

    reg = AgentRunnerRegistry(default_agent="orchestrator", builder=builder)
    assert reg.loaded() == []

    first = reg.get("intel")
    second = reg.get("intel")

    assert first is second
    assert call_count["n"] == 1
    assert reg.loaded() == ["intel"]


def test_get_builds_different_runners_per_name():
    def builder(name: str):
        m = MagicMock()
        m.agent_name = name
        return m

    reg = AgentRunnerRegistry(default_agent="orchestrator", builder=builder)
    a = reg.get("content-scott")
    b = reg.get("dev-mgr")

    assert a is not b
    assert a.agent_name == "content-scott"
    assert b.agent_name == "dev-mgr"
    assert set(reg.loaded()) == {"content-scott", "dev-mgr"}


def test_get_empty_string_falls_through_to_default():
    built = {}

    def builder(name: str):
        built[name] = MagicMock()
        return built[name]

    reg = AgentRunnerRegistry(default_agent="orchestrator", builder=builder)
    runner = reg.get("")
    assert runner is built["orchestrator"]


def test_register_preseeds_and_skips_builder():
    def builder(_: str):
        raise AssertionError("builder should not run for pre-seeded agent")

    preseeded = MagicMock()
    reg = AgentRunnerRegistry(default_agent="orchestrator", builder=builder)
    reg.register("orchestrator", preseeded)

    assert reg.get(None) is preseeded
    assert reg.get("orchestrator") is preseeded
    assert reg.loaded() == ["orchestrator"]


def test_loaded_returns_sorted_names():
    def builder(name: str):
        return MagicMock()

    reg = AgentRunnerRegistry(default_agent="orchestrator", builder=builder)
    reg.get("zeta")
    reg.get("alpha")
    reg.get("mu")

    assert reg.loaded() == ["alpha", "mu", "zeta"]
