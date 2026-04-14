"""Tests for AgentOverride model + round-trip."""

from __future__ import annotations

from gclaw.heartbeat.config import HeartbeatConfig
from gclaw.models.agent_config import (
    AgentIdentity,
    AgentModelSpec,
    AgentOverride,
    AgentSubagentsSpec,
    AgentToolsSpec,
    ThinkingLevel,
)


def test_round_trip_full_override():
    o = AgentOverride(
        agent_name="dev-mgr",
        identity=AgentIdentity(
            display_name="Dev Manager",
            emoji="🛠",
            description="Handles code",
        ),
        model=AgentModelSpec(
            primary="My OpenAI/gpt-4o",
            fallbacks=["gemini-2.5-flash"],
            thinking=ThinkingLevel.HIGH,
            params={"temperature": 0.2},
        ),
        tools=AgentToolsSpec(
            profile="coding",
            allow=["get_current_diff"],
            deny=["read_local_file"],
        ),
        subagents=AgentSubagentsSpec(allow=["dev-mgr"]),
        skills=["commit-message"],
        heartbeat=HeartbeatConfig(enabled=True, every="10m"),
        body_override="You are Dev Mgr.",
        soul_overlay="Be concise.",
    )
    data = o.to_firestore_dict()
    # Firestore dict should drop agent_name (doc id is the name).
    assert "agent_name" not in data
    back = AgentOverride.from_firestore_dict("dev-mgr", data)
    assert back.agent_name == "dev-mgr"
    assert back.identity.display_name == "Dev Manager"
    assert back.model.primary == "My OpenAI/gpt-4o"
    assert back.model.thinking == ThinkingLevel.HIGH
    assert back.tools.allow == ["get_current_diff"]
    assert back.tools.deny == ["read_local_file"]
    assert back.subagents.allow == ["dev-mgr"]
    assert back.skills == ["commit-message"]
    assert back.heartbeat.every == "10m"
    assert back.body_override == "You are Dev Mgr."
    assert back.soul_overlay == "Be concise."


def test_legacy_dict_back_compat():
    legacy = {
        "identity": {},
        "body": "legacy body",
        "system_prompt": "legacy sysprompt",
    }
    back = AgentOverride.from_firestore_dict("foo", legacy)
    assert back.body_override == "legacy body"
    assert back.system_prompt_override == "legacy sysprompt"


def test_defaults_are_safe():
    o = AgentOverride(agent_name="x")
    assert o.enabled is True
    assert o.is_standalone is False
    assert o.tools.allow == []
    assert o.tools.deny == []
    assert o.skills is None
    assert o.subagents.allow is None
    assert o.heartbeat is None
    assert o.identity.display_name is None
