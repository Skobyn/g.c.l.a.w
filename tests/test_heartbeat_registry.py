"""Tests for HeartbeatRegistry."""

from __future__ import annotations

from unittest.mock import MagicMock

from gclaw.heartbeat.config import HeartbeatConfig
from gclaw.heartbeat.registry import HeartbeatRegistry


def test_register_and_get():
    reg = HeartbeatRegistry()
    service = MagicMock()
    cfg = HeartbeatConfig(enabled=True, every="30m")
    reg.register("orchestrator", service, cfg)

    assert reg.get("orchestrator") is service
    assert reg.get_config("orchestrator") is cfg


def test_get_returns_none_for_unknown():
    reg = HeartbeatRegistry()
    assert reg.get("missing") is None
    assert reg.get_config("missing") is None


def test_all_agents_and_items():
    reg = HeartbeatRegistry()
    s1, s2 = MagicMock(), MagicMock()
    c1 = HeartbeatConfig(enabled=True, every="1m")
    c2 = HeartbeatConfig(enabled=False, every="5m")
    reg.register("a", s1, c1)
    reg.register("b", s2, c2)

    assert set(reg.all_agents()) == {"a", "b"}
    items = dict((name, (svc, cfg)) for name, svc, cfg in reg.items())
    assert items["a"] == (s1, c1)
    assert items["b"] == (s2, c2)


def test_register_overwrites():
    reg = HeartbeatRegistry()
    s1, s2 = MagicMock(), MagicMock()
    cfg = HeartbeatConfig(enabled=True, every="1m")
    reg.register("a", s1, cfg)
    reg.register("a", s2, cfg)
    assert reg.get("a") is s2
    assert reg.all_agents() == ["a"]
