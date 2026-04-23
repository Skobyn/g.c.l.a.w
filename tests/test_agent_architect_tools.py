"""Tests for agent_architect_tools — file ops + Firestore registration."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from gclaw.tools import agent_architect_tools as aat


@pytest.fixture(autouse=True)
def _reset_service():
    """Each test starts with no service wired."""
    aat.set_agent_config_service(None)
    yield
    aat.set_agent_config_service(None)


@pytest.fixture
def config_dir(tmp_path: Path, monkeypatch) -> Path:
    """A fresh GCLAW_CONFIG_DIR with empty agents/ and soul/ trees."""
    (tmp_path / "agents").mkdir()
    (tmp_path / "soul").mkdir()
    monkeypatch.setenv("GCLAW_CONFIG_DIR", str(tmp_path))
    return tmp_path


# --- name validation ---


def test_validate_name_rejects_empty():
    with pytest.raises(ValueError):
        aat._validate_name("")


def test_validate_name_rejects_traversal():
    with pytest.raises(ValueError):
        aat._validate_name("../etc")
    with pytest.raises(ValueError):
        aat._validate_name("foo/bar")


def test_validate_name_rejects_leading_special():
    for n in ("-foo", "_foo", ".foo"):
        with pytest.raises(ValueError):
            aat._validate_name(n)


def test_validate_name_accepts_kebab_and_snake():
    aat._validate_name("workspace-mgr")
    aat._validate_name("research_mgr")
    aat._validate_name("Agent99")


# --- read tools ---


def test_read_agent_file_returns_not_found(config_dir):
    out = aat.read_agent_file("nonexistent")
    assert out.startswith("NOT FOUND")


def test_read_agent_file_returns_body(config_dir):
    (config_dir / "agents" / "demo.md").write_text("hello body\n")
    out = aat.read_agent_file("demo")
    assert out == "hello body\n"


def test_list_agent_files_lists_existing(config_dir):
    (config_dir / "agents" / "alpha.md").write_text("x")
    (config_dir / "agents" / "beta.md").write_text("y")
    (config_dir / "agents" / "ignored.txt").write_text("z")
    out = aat.list_agent_files()
    names = out.splitlines()
    assert names == ["alpha", "beta"]


def test_list_agent_files_empty(config_dir):
    assert aat.list_agent_files() == "(no agents)"


# --- write tools ---


def test_write_agent_file_refuses_empty_body(config_dir):
    out = aat.write_agent_file("foo", "")
    assert out.startswith("ERROR")
    assert not (config_dir / "agents" / "foo.md").exists()


def test_write_agent_file_creates_file(config_dir):
    out = aat.write_agent_file("foo", "You are foo.")
    assert out.startswith("OK: created")
    assert (config_dir / "agents" / "foo.md").read_text() == "You are foo.\n"


def test_write_agent_file_refuses_overwrite_by_default(config_dir):
    aat.write_agent_file("foo", "first")
    out = aat.write_agent_file("foo", "second")
    assert out.startswith("ERROR")
    # Original content preserved.
    assert (config_dir / "agents" / "foo.md").read_text() == "first\n"


def test_write_agent_file_overwrites_when_allowed(config_dir):
    aat.write_agent_file("foo", "first")
    out = aat.write_agent_file("foo", "second", allow_overwrite=True)
    assert out.startswith("OK: overwrote")
    assert (config_dir / "agents" / "foo.md").read_text() == "second\n"


def test_write_agent_file_refuses_traversal(config_dir):
    out = aat.write_agent_file("../escape", "nope")
    assert out.startswith("ERROR")


def test_write_soul_file_creates(config_dir):
    out = aat.write_soul_file("foo", "voice", allow_overwrite=False)
    assert out.startswith("OK: created")
    assert (config_dir / "soul" / "foo.md").read_text() == "voice\n"


# --- standalone registration (Firestore-backed) ---


def test_register_standalone_raises_without_service():
    with pytest.raises(RuntimeError, match="agent_config_service not configured"):
        aat.register_standalone_agent("foo", "body")


def test_register_standalone_calls_service():
    svc = MagicMock()
    fake_override = MagicMock()
    fake_override.agent_name = "foo"
    fake_override.model.primary = "gemini-2.5-flash"
    svc.create_standalone.return_value = fake_override
    aat.set_agent_config_service(svc)

    out = aat.register_standalone_agent(
        agent_name="foo",
        body="You are foo.",
        display_name="Foo",
        description="Does foo things",
        model_primary="gemini-2.5-flash",
    )
    assert out.startswith("OK")
    svc.create_standalone.assert_called_once()
    kwargs = svc.create_standalone.call_args.kwargs
    assert kwargs["agent_name"] == "foo"
    assert kwargs["body"] == "You are foo."
    assert kwargs["display_name"] == "Foo"
    assert kwargs["description"] == "Does foo things"
    assert kwargs["model_primary"] == "gemini-2.5-flash"


def test_register_standalone_passes_none_for_blank_optionals():
    """Empty strings should map to None so the service treats them as
    'not provided' (a literal "" identity name would clobber the
    sensible default in admin views)."""
    svc = MagicMock()
    svc.create_standalone.return_value = MagicMock(
        agent_name="foo", model=MagicMock(primary=None),
    )
    aat.set_agent_config_service(svc)
    aat.register_standalone_agent(agent_name="foo", body="b")
    kwargs = svc.create_standalone.call_args.kwargs
    assert kwargs["display_name"] is None
    assert kwargs["description"] is None
    assert kwargs["soul_overlay"] is None
    assert kwargs["model_primary"] is None


def test_register_standalone_surfaces_value_error_as_text():
    svc = MagicMock()
    svc.create_standalone.side_effect = ValueError(
        "agent 'foo' already has a baseline .md"
    )
    aat.set_agent_config_service(svc)
    out = aat.register_standalone_agent("foo", "body")
    assert out.startswith("ERROR:")
    assert "baseline" in out


# --- update_agent_model ---


def test_update_agent_model_patches_via_service():
    svc = MagicMock()
    fake = MagicMock()
    fake.model.primary = "claude-haiku-4-5"
    svc.upsert_override.return_value = fake
    aat.set_agent_config_service(svc)

    out = aat.update_agent_model("foo", "claude-haiku-4-5")
    assert out.startswith("OK")
    svc.upsert_override.assert_called_once_with(
        "foo", {"model": {"primary": "claude-haiku-4-5"}}
    )


def test_update_agent_model_requires_primary():
    aat.set_agent_config_service(MagicMock())
    out = aat.update_agent_model("foo", "")
    assert out.startswith("ERROR")


# --- list_registered_agents ---


def test_list_registered_agents_formats_per_kind():
    svc = MagicMock()
    svc.list_agents.return_value = [
        {"name": "alpha", "is_standalone": True, "has_override": True,
         "model_ref": "gemini-2.5-flash"},
        {"name": "beta", "is_standalone": False, "has_override": True,
         "model_ref": "claude-haiku-4-5"},
        {"name": "gamma", "is_standalone": False, "has_override": False,
         "model_ref": None},
    ]
    aat.set_agent_config_service(svc)
    out = aat.list_registered_agents()
    lines = out.splitlines()
    assert lines == [
        "alpha [standalone] model=gemini-2.5-flash",
        "beta [override-on-baseline] model=claude-haiku-4-5",
        "gamma [baseline] model=<router-default>",
    ]


def test_list_registered_agents_empty():
    svc = MagicMock()
    svc.list_agents.return_value = []
    aat.set_agent_config_service(svc)
    assert aat.list_registered_agents() == "(no agents)"
