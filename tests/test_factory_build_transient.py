"""Tests for ``AgentFactory.build_transient`` (ADR-0006).

The transient build path produces a live ``LlmAgent`` from a (body,
soul, tools) tuple without persisting to Firestore and without
requiring a baseline ``agents/<name>.md`` file. Used by the
agent-architect to score drafts via eval before registration.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from google.adk.agents import LlmAgent

from gclaw.agents.factory import AgentFactory
from gclaw.config.loader import ConfigLoader


@pytest.fixture
def config_dir(tmp_path):
    """A config dir with only a soul base + one named overlay.

    Notably no ``agents/<name>.md`` files — the transient path must
    work without them.
    """
    soul_dir = tmp_path / "soul"
    soul_dir.mkdir()
    (soul_dir / "base.md").write_text("You are a helpful gclaw agent.\n")
    (soul_dir / "draft-overlay.md").write_text(
        "Voice: friendly, terse, lowercase.\n"
    )
    (tmp_path / "agents").mkdir()
    return tmp_path


@pytest.fixture
def factory(config_dir):
    loader = ConfigLoader(str(config_dir))
    return AgentFactory(loader=loader, default_model="gemini-2.5-flash")


def test_build_transient_returns_llm_agent(factory):
    agent = factory.build_transient(
        agent_name="finance-mgr",
        body="You summarize Plaid balances on demand.",
    )
    assert isinstance(agent, LlmAgent)
    # Names get safe-mangled the same way the persistent path does.
    assert agent.name == "finance_mgr"
    # Body should land verbatim in the Agent Role block.
    assert "summarize Plaid balances" in agent.instruction
    # Soul base flows through.
    assert "helpful gclaw agent" in agent.instruction


def test_build_transient_does_not_persist_override(config_dir):
    """The transient path must not call the agent_config_service.

    We wire a fake service that records every call and assert
    ``get_override`` was NOT used during the build (since transient
    drafts have no override and must not pretend to have one).
    """
    fake_service = MagicMock()
    fake_service.get_override.return_value = None
    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(
        loader=loader,
        default_model="gemini-2.5-flash",
        agent_config_service=fake_service,
    )

    agent = factory.build_transient(
        agent_name="finance-mgr",
        body="You summarize Plaid balances on demand.",
    )
    assert agent is not None
    # No override lookup, no upsert, no create_standalone — the build
    # must not touch Firestore.
    fake_service.get_override.assert_not_called()
    fake_service.upsert_override.assert_not_called()
    fake_service.create_standalone.assert_not_called()
    # Post-build: no override exists for this name (regression check
    # against accidental persistence).
    assert fake_service.get_override("finance-mgr") is None


def test_build_transient_layers_soul_overlay(factory):
    agent = factory.build_transient(
        agent_name="finance-mgr",
        body="You summarize Plaid balances on demand.",
        soul_overlay="draft-overlay",
    )
    assert "Voice: friendly, terse, lowercase." in agent.instruction
    # Base soul is still present underneath the overlay.
    assert "helpful gclaw agent" in agent.instruction


def test_build_transient_uses_provided_tools(factory):
    def fetch_balance(account_id: str) -> str:
        """Fetch a balance by id."""
        return account_id

    def list_accounts() -> str:
        """List all accounts."""
        return ""

    agent = factory.build_transient(
        agent_name="finance-mgr",
        body="You summarize Plaid balances.",
        tools=[fetch_balance, list_accounts],
    )
    # ADK stores tools as wrapped objects; we check by extracted name.
    names = {AgentFactory._tool_name(t) for t in agent.tools}
    assert "fetch_balance" in names
    assert "list_accounts" in names
    assert len(agent.tools) == 2


def test_build_transient_works_without_baseline_file(factory):
    """The transient path must NOT require an agents/<name>.md file.

    The whole point of this method is scoring drafts before they're
    written anywhere — if it required a baseline, the architect
    couldn't use it for new agents.
    """
    # No agents/finance-mgr.md exists — build_transient must not raise.
    agent = factory.build_transient(
        agent_name="finance-mgr",
        body="You summarize Plaid balances.",
    )
    assert agent.instruction  # something got assembled


def test_build_transient_explicit_model_overrides_default(factory):
    agent = factory.build_transient(
        agent_name="finance-mgr",
        body="You summarize Plaid balances.",
        model="custom-model-id",
    )
    assert agent.model == "custom-model-id"


def test_build_transient_falls_back_to_default_model(factory):
    agent = factory.build_transient(
        agent_name="finance-mgr",
        body="You summarize Plaid balances.",
    )
    # No router, no frontmatter (no file), no explicit model →
    # default_model wins.
    assert agent.model == "gemini-2.5-flash"


def test_build_transient_sets_no_before_agent_callback(factory):
    """Memory recall callbacks must NOT fire on transient builds.

    Recall would hit Vertex Memory Bank per turn and dominate the eval
    pass wall-clock. The transient path enforces this by never wiring
    a ``before_agent_callback``.
    """
    agent = factory.build_transient(
        agent_name="finance-mgr",
        body="You summarize Plaid balances.",
    )
    # ADK sets unset callbacks to None or an empty list depending on
    # the version; both are acceptable as "no callback wired".
    cb = getattr(agent, "before_agent_callback", None)
    assert not cb


def test_build_transient_omits_user_profile_block(factory, tmp_path):
    """The transient path skips the user.md injection.

    Even when the orchestrator's persistent build would normally see
    ``# About the User``, transient drafts shouldn't — the eval run
    isn't supposed to depend on personal context.
    """
    # Drop a user.md alongside config_dir to confirm it's ignored.
    (factory._loader._config_dir + "/user.md")  # type: ignore[operator]
    import os
    user_md = os.path.join(factory._loader._config_dir, "user.md")
    with open(user_md, "w") as f:
        f.write("Name: Sam\n")

    agent = factory.build_transient(
        agent_name="orchestrator",
        body="root",
    )
    assert "About the User" not in agent.instruction
    assert "Name: Sam" not in agent.instruction
