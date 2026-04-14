"""Tests for per-agent frontmatter model picker."""

from __future__ import annotations

import logging

import pytest

from gclaw.agents.factory import AgentFactory
from gclaw.catalog.model_resolver import resolve_agent_model
from gclaw.catalog.service import CatalogService
from gclaw.config.loader import ConfigLoader
from gclaw.models.catalog import AgentModelRef, ProviderKind
from gclaw.models.model_config import ModelEndpoint, RoutingRule, TaskProfile
from gclaw.routing.router import ModelRouter

from _catalog_fakes import FakeModelRepo, FakeProviderRepo


@pytest.fixture
def config_dir(tmp_path):
    soul_dir = tmp_path / "soul"
    soul_dir.mkdir()
    (soul_dir / "base.md").write_text("You are helpful.\n")

    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "plain.md").write_text(
        "Plain agent — no frontmatter.\n"
    )
    (agents_dir / "string-ref.md").write_text(
        "---\nmodel: \"My OpenAI/gpt-4o\"\n---\nDev manager body.\n"
    )
    (agents_dir / "bare-ref.md").write_text(
        "---\nmodel: \"gpt-4o\"\n---\nBare ref body.\n"
    )
    (agents_dir / "dict-ref.md").write_text(
        "---\n"
        "model:\n"
        "  name: \"My OpenAI/gpt-4o\"\n"
        "  params:\n"
        "    temperature: 0.2\n"
        "    max_tokens: 4096\n"
        "---\n"
        "Dict ref body.\n"
    )
    (agents_dir / "missing.md").write_text(
        "---\nheartbeat:\n  enabled: false\n---\nNo model key.\n"
    )
    return tmp_path


@pytest.fixture
def loader(config_dir):
    return ConfigLoader(str(config_dir))


# --- load_agent_model_ref ----------------------------------------------------


def test_load_agent_model_ref_string(loader):
    ref = loader.load_agent_model_ref("string-ref")
    assert ref is not None
    assert ref.name == "My OpenAI/gpt-4o"
    assert ref.params is None


def test_load_agent_model_ref_dict_with_params(loader):
    ref = loader.load_agent_model_ref("dict-ref")
    assert ref is not None
    assert ref.name == "My OpenAI/gpt-4o"
    assert ref.params is not None
    assert ref.params.temperature == 0.2
    assert ref.params.max_tokens == 4096


def test_load_agent_model_ref_missing_returns_none(loader):
    assert loader.load_agent_model_ref("plain") is None
    assert loader.load_agent_model_ref("missing") is None


# --- resolve_agent_model -----------------------------------------------------


def _make_catalog(with_openai: bool = True, with_duplicate: bool = False):
    svc = CatalogService(FakeProviderRepo(), FakeModelRepo())
    if with_openai:
        p = svc.create_provider(
            name="My OpenAI", kind=ProviderKind.OPENAI, enabled=True
        )
        svc.create_model(
            provider_id=p.id,
            model_id="gpt-4o",
            display_name="GPT-4o",
        )
    if with_duplicate:
        p2 = svc.create_provider(
            name="Other OpenAI", kind=ProviderKind.OPENAI, enabled=True
        )
        svc.create_model(
            provider_id=p2.id,
            model_id="gpt-4o",
            display_name="GPT-4o alt",
        )
    return svc


def test_resolve_agent_model_provider_slash_model():
    svc = _make_catalog()
    ref = AgentModelRef(name="My OpenAI/gpt-4o")
    resolved = resolve_agent_model(ref, svc)
    assert resolved is not None
    provider, model = resolved
    assert provider.name == "My OpenAI"
    assert model.model_id == "gpt-4o"


def test_resolve_agent_model_bare_id():
    svc = _make_catalog()
    ref = AgentModelRef(name="gpt-4o")
    resolved = resolve_agent_model(ref, svc)
    assert resolved is not None
    provider, model = resolved
    assert provider.name == "My OpenAI"
    assert model.model_id == "gpt-4o"


def test_resolve_agent_model_not_found_returns_none():
    svc = _make_catalog(with_openai=False)
    ref = AgentModelRef(name="gpt-4o")
    assert resolve_agent_model(ref, svc) is None

    ref2 = AgentModelRef(name="Nope/whatever")
    assert resolve_agent_model(ref2, svc) is None


def test_resolve_agent_model_ambiguous_warns(caplog):
    svc = _make_catalog(with_duplicate=True)
    ref = AgentModelRef(name="gpt-4o")
    with caplog.at_level(logging.WARNING, logger="gclaw.catalog.model_resolver"):
        resolved = resolve_agent_model(ref, svc)
    assert resolved is not None
    assert any("ambiguous" in r.message for r in caplog.records)


# --- AgentFactory integration ------------------------------------------------


def test_factory_frontmatter_model_uses_catalog(config_dir):
    loader = ConfigLoader(str(config_dir))
    svc = _make_catalog()
    router = ModelRouter(
        endpoints={
            "gemini-pro": ModelEndpoint(
                name="gemini-pro",
                endpoint_id="gemini-2.5-pro",
                max_context_tokens=1_000_000,
            )
        },
        rules=[
            RoutingRule(
                task_profile=TaskProfile.ORCHESTRATION,
                model_name="gemini-pro",
            )
        ],
        default_model="gemini-2.5-flash",
    )
    factory = AgentFactory(
        loader=loader,
        default_model="gemini-2.5-flash",
        model_router=router,
        catalog_service=svc,
    )
    agent = factory.build(agent_name="string-ref")
    # OpenAI wraps in LiteLlm — not a bare string.
    assert agent.model != "gemini-2.5-pro"
    assert agent.model != "gemini-2.5-flash"
    # LiteLlm carries the wrapped model id.
    assert hasattr(agent.model, "model")
    assert "gpt-4o" in agent.model.model


def test_factory_without_frontmatter_uses_router(config_dir):
    loader = ConfigLoader(str(config_dir))
    svc = _make_catalog()
    router = ModelRouter(
        endpoints={
            "gemini-pro": ModelEndpoint(
                name="gemini-pro",
                endpoint_id="gemini-2.5-pro",
                max_context_tokens=1_000_000,
            )
        },
        rules=[
            RoutingRule(
                task_profile=TaskProfile.ORCHESTRATION,
                model_name="gemini-pro",
            )
        ],
        default_model="gemini-2.5-flash",
    )
    factory = AgentFactory(
        loader=loader,
        default_model="gemini-2.5-flash",
        model_router=router,
        catalog_service=svc,
    )
    # 'plain' has no frontmatter → should fall back to router default.
    agent = factory.build(agent_name="plain")
    # Router uses default_model when no rule matches "plain".
    assert agent.model == "gemini-2.5-flash"


def test_factory_no_frontmatter_empty_catalog_falls_back(config_dir):
    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(
        loader=loader,
        default_model="gemini-2.5-flash",
    )
    agent = factory.build(agent_name="plain")
    assert agent.model == "gemini-2.5-flash"


def test_factory_frontmatter_missing_catalog_falls_back(config_dir, caplog):
    """Frontmatter present but no catalog → warn and fall back."""
    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(
        loader=loader,
        default_model="gemini-2.5-flash",
    )
    with caplog.at_level(logging.WARNING, logger="gclaw.agents.factory"):
        agent = factory.build(agent_name="string-ref")
    assert agent.model == "gemini-2.5-flash"
