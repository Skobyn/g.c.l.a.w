"""AgentFactory.resolve_model_chain — primary + fallbacks via catalog."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from gclaw.agents.factory import AgentFactory
from gclaw.catalog.service import CatalogService
from gclaw.config.loader import ConfigLoader
from gclaw.models.agent_config import AgentModelSpec, AgentOverride
from gclaw.models.catalog import ProviderKind

from _catalog_fakes import FakeModelRepo, FakeProviderRepo


@pytest.fixture
def loader(tmp_path: Path) -> ConfigLoader:
    (tmp_path / "agents").mkdir()
    (tmp_path / "soul").mkdir()
    (tmp_path / "soul" / "base.md").write_text("base soul")
    (tmp_path / "agents" / "test-agent.md").write_text("You are test.")
    return ConfigLoader(str(tmp_path))


@pytest.fixture
def catalog() -> CatalogService:
    svc = CatalogService(FakeProviderRepo(), FakeModelRepo())
    google = svc.create_provider(
        name="Google", kind=ProviderKind.GOOGLE_GEMINI,
    )
    svc.create_model(
        provider_id=google.id,
        model_id="gemini-2.5-flash",
        display_name="Gemini Flash",
    )
    svc.create_model(
        provider_id=google.id,
        model_id="gemini-2.0-flash",
        display_name="Gemini 2.0 Flash",
    )
    svc.create_model(
        provider_id=google.id,
        model_id="gemini-1.5-pro",
        display_name="Gemini 1.5 Pro",
    )
    return svc


class _StubOverrideSvc:
    def __init__(self, override):
        self._o = override

    def get_override(self, name):
        return self._o if name == "test-agent" else None


def test_resolve_chain_returns_primary_plus_fallbacks(loader, catalog):
    override = AgentOverride(
        agent_name="test-agent",
        model=AgentModelSpec(
            primary="Google/gemini-2.5-flash",
            fallbacks=["Google/gemini-2.0-flash", "Google/gemini-1.5-pro"],
        ),
    )
    factory = AgentFactory(
        loader=loader,
        catalog_service=catalog,
        agent_config_service=_StubOverrideSvc(override),
    )
    chain = factory.resolve_model_chain("test-agent")
    assert len(chain) == 3
    # Gemini providers return bare model id strings.
    assert chain[0] == "gemini-2.5-flash"
    assert chain[1] == "gemini-2.0-flash"
    assert chain[2] == "gemini-1.5-pro"


def test_resolve_chain_skips_unresolvable_fallback(loader, catalog, caplog):
    override = AgentOverride(
        agent_name="test-agent",
        model=AgentModelSpec(
            primary="Google/gemini-2.5-flash",
            fallbacks=["Google/does-not-exist", "Google/gemini-1.5-pro"],
        ),
    )
    factory = AgentFactory(
        loader=loader,
        catalog_service=catalog,
        agent_config_service=_StubOverrideSvc(override),
    )
    with caplog.at_level("WARNING"):
        chain = factory.resolve_model_chain("test-agent")
    assert chain == ["gemini-2.5-flash", "gemini-1.5-pro"]
    assert any("did not resolve" in rec.message or "not found" in rec.message
               for rec in caplog.records)


def test_resolve_chain_no_override_uses_router(loader):
    router = MagicMock()
    router.build_adk_model_for_agent.return_value = "router-model"
    factory = AgentFactory(
        loader=loader,
        model_router=router,
        agent_config_service=_StubOverrideSvc(None),
    )
    chain = factory.resolve_model_chain("test-agent")
    assert chain == ["router-model"]
    router.build_adk_model_for_agent.assert_called_once_with("test-agent")


def test_resolve_chain_no_router_no_override_returns_empty(loader):
    factory = AgentFactory(loader=loader)
    assert factory.resolve_model_chain("test-agent") == []
