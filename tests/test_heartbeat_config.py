"""Tests for HeartbeatConfig and parse_duration_ms."""

import pytest

from gclaw.heartbeat.config import (
    ActiveHours,
    HeartbeatConfig,
    parse_duration_ms,
)


def test_parse_minutes():
    assert parse_duration_ms("30m") == 1_800_000


def test_parse_hours():
    assert parse_duration_ms("2h") == 7_200_000


def test_parse_seconds():
    assert parse_duration_ms("15s") == 15_000


def test_parse_milliseconds():
    assert parse_duration_ms("500ms") == 500


def test_parse_days():
    assert parse_duration_ms("1d") == 86_400_000


def test_parse_default_unit_is_minutes():
    # No suffix → minutes.
    assert parse_duration_ms("5") == 300_000


def test_parse_decimal():
    assert parse_duration_ms("1.5h") == 5_400_000


def test_parse_case_insensitive():
    assert parse_duration_ms("2H") == 7_200_000


def test_parse_whitespace_tolerated():
    assert parse_duration_ms(" 10m ") == 600_000


def test_parse_invalid_raises():
    with pytest.raises(ValueError):
        parse_duration_ms("bad")


def test_parse_negative_raises():
    with pytest.raises(ValueError):
        parse_duration_ms("-5m")


def test_parse_empty_raises():
    with pytest.raises(ValueError):
        parse_duration_ms("")


def test_config_defaults():
    cfg = HeartbeatConfig()
    assert cfg.enabled is False
    assert cfg.every == "30m"
    assert cfg.session == "main"
    assert cfg.isolated_session is False
    assert cfg.light_context is False
    assert cfg.timeout_seconds == 120
    assert cfg.ack_max_chars == 30
    assert cfg.active_hours is None
    assert cfg.target == "none"
    assert cfg.channel is None
    assert cfg.include_reasoning is False
    assert cfg.prompt is None


def test_config_with_active_hours():
    cfg = HeartbeatConfig(
        enabled=True,
        every="15m",
        active_hours=ActiveHours(
            start="07:00", end="23:00", timezone="America/Los_Angeles"
        ),
    )
    assert cfg.active_hours is not None
    assert cfg.active_hours.start == "07:00"
    assert cfg.active_hours.timezone == "America/Los_Angeles"


def test_config_target_literal_enforced():
    with pytest.raises(Exception):
        HeartbeatConfig(target="invalid")  # type: ignore[arg-type]
