"""Tests for AgentConfigService merge behaviour."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from gclaw.config.agent_config_service import AgentConfigService
from gclaw.config.loader import ConfigLoader
from gclaw.heartbeat.config import HeartbeatConfig
from gclaw.models.agent_config import (
    AgentIdentity,
    AgentModelSpec,
    AgentOverride,
    AgentToolsSpec,
)


class FakeOverrideRepo:
    def __init__(self):
        self.store: dict[str, AgentOverride] = {}

    def create(self, o):
        self.store[o.agent_name] = o
        return o

    def get(self, name):
        return self.store.get(name)

    def update(self, o):
        self.store[o.agent_name] = o
        return o

    def delete(self, name):
        self.store.pop(name, None)

    def list_all(self):
        return list(self.store.values())


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    (tmp_path / "agents").mkdir()
    (tmp_path / "soul").mkdir()
    (tmp_path / "soul" / "base.md").write_text("# Base soul")
    (tmp_path / "agents" / "dev-mgr.md").write_text(
        "---\nmodel: \"Prov/gpt-4o\"\nheartbeat:\n  enabled: true\n"
        "  every: 20m\n---\nYou are dev.\n"
    )
    (tmp_path / "agents" / "home-mgr.md").write_text(
        "You are home.\n"
    )
    return tmp_path


@pytest.fixture
def service(config_dir: Path):
    repo = FakeOverrideRepo()
    loader = ConfigLoader(str(config_dir))
    svc = AgentConfigService(
        override_repo=repo,
        loader=loader,
        skill_registry=None,
        agents_dir=config_dir / "agents",
    )
    return svc, repo, loader


def test_get_effective_file_only(service):
    svc, _, _ = service
    cfg = svc.get_effective_config("dev-mgr")
    assert cfg["has_baseline"] is True
    assert cfg["has_override"] is False
    assert cfg["body"].startswith("You are dev.")
    assert cfg["model"]["effective_primary"] == "Prov/gpt-4o"
    assert cfg["heartbeat"]["every"] == "20m"
    assert cfg["is_standalone"] is False


def test_get_effective_with_override(service):
    svc, repo, _ = service
    repo.create(AgentOverride(
        agent_name="dev-mgr",
        identity=AgentIdentity(display_name="Dev!"),
        model=AgentModelSpec(primary="Other/model-x"),
        body_override="OVERRIDDEN",
        heartbeat=HeartbeatConfig(enabled=False, every="5m"),
    ))
    cfg = svc.get_effective_config("dev-mgr")
    assert cfg["has_override"] is True
    assert cfg["body"] == "OVERRIDDEN"
    assert cfg["model"]["effective_primary"] == "Other/model-x"
    assert cfg["heartbeat"]["enabled"] is False
    assert cfg["identity"]["display_name"] == "Dev!"


def test_standalone_override(service):
    svc, _, _ = service
    svc.create_standalone(
        agent_name="my-agent",
        body="Hello, world",
        display_name="Mine",
    )
    cfg = svc.get_effective_config("my-agent")
    assert cfg["has_baseline"] is False
    assert cfg["has_override"] is True
    assert cfg["is_standalone"] is True
    assert cfg["body"] == "Hello, world"


def test_list_agents_union(service):
    svc, repo, _ = service
    svc.create_standalone(agent_name="zzz-standalone", body="x")
    names = [e["name"] for e in svc.list_agents()]
    assert "dev-mgr" in names
    assert "home-mgr" in names
    assert "zzz-standalone" in names
    # Ensure standalone marked correctly
    for e in svc.list_agents():
        if e["name"] == "zzz-standalone":
            assert e["is_standalone"] is True
            assert e["has_baseline"] is False
        if e["name"] == "dev-mgr":
            assert e["has_baseline"] is True


def test_delete_override_reverts_file_backed(service):
    svc, repo, _ = service
    repo.create(AgentOverride(
        agent_name="dev-mgr",
        body_override="CUSTOM",
    ))
    result = svc.delete_override("dev-mgr")
    assert result == {"deleted": True, "reverted_to_baseline": True}
    cfg = svc.get_effective_config("dev-mgr")
    assert cfg["body"].startswith("You are dev.")
    assert cfg["has_override"] is False


def test_delete_override_fully_removes_standalone(service):
    svc, _, _ = service
    svc.create_standalone(agent_name="gone", body="x")
    result = svc.delete_override("gone")
    assert result == {"deleted": True, "reverted_to_baseline": False}
    with pytest.raises(FileNotFoundError):
        svc.get_effective_config("gone")


def test_upsert_patch_nested_identity(service):
    svc, _, _ = service
    svc.upsert_override("dev-mgr", {"identity": {"display_name": "D"}})
    svc.upsert_override("dev-mgr", {"identity": {"emoji": "🦾"}})
    cfg = svc.get_effective_config("dev-mgr")
    assert cfg["identity"]["display_name"] == "D"
    assert cfg["identity"]["emoji"] == "🦾"


def test_upsert_tools_lists_replace(service):
    svc, _, _ = service
    svc.upsert_override("dev-mgr", {"tools": {"allow": ["a", "b"]}})
    svc.upsert_override("dev-mgr", {"tools": {"allow": ["c"]}})
    cfg = svc.get_effective_config("dev-mgr")
    assert cfg["tools"]["allow"] == ["c"]


def test_loader_override_provider_wins(service):
    svc, repo, loader = service
    repo.create(AgentOverride(
        agent_name="dev-mgr",
        body_override="FROM-OVERRIDE",
        heartbeat=HeartbeatConfig(enabled=False, every="1h"),
        model=AgentModelSpec(primary="Zoo/bar"),
    ))
    loader.set_override_provider(svc.get_override)
    assert loader.load_agent("dev-mgr") == "FROM-OVERRIDE"
    hb = loader.load_agent_heartbeat_config("dev-mgr")
    assert hb.every == "1h"
    ref = loader.load_agent_model_ref("dev-mgr")
    assert ref.name == "Zoo/bar"


def test_standalone_requires_no_existing_baseline(service):
    svc, _, _ = service
    with pytest.raises(ValueError):
        svc.create_standalone(agent_name="dev-mgr", body="x")


def test_read_baseline(service):
    svc, _, _ = service
    raw = svc.read_baseline("dev-mgr")
    assert raw is not None and "You are dev." in raw
    assert svc.read_baseline("nonexistent") is None
