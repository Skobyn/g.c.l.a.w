"""Tests for AgentFactory output_key support and ADK model resolution."""

import os
from unittest.mock import MagicMock

import pytest

from gclaw.agents.factory import AgentFactory
from gclaw.config.loader import ConfigLoader
from gclaw.models.model_config import ModelEndpoint, RoutingRule, TaskProfile
from gclaw.routing.router import ModelRouter


@pytest.fixture
def config_dir(tmp_path):
    soul_dir = tmp_path / "soul"
    soul_dir.mkdir()
    (soul_dir / "base.md").write_text("Base personality.\n")
    (soul_dir / "dev.md").write_text("Dev overlay.\n")
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "dev-mgr.md").write_text("Dev manager role.\n")
    (agents_dir / "orchestrator.md").write_text("Orchestrator role.\n")
    return tmp_path


@pytest.fixture
def router():
    endpoints = {
        "gemini-flash": ModelEndpoint(
            name="gemini-flash", endpoint_id="gemini-2.5-flash", provider="gemini",
        ),
        "nemotron-3-super": ModelEndpoint(
            name="nemotron-3-super",
            endpoint_id="nvidia/nemotron-3-super-120b-a12b:free",
            provider="openrouter",
        ),
    }
    rules = [
        RoutingRule(task_profile=TaskProfile.ORCHESTRATION, model_name="gemini-flash"),
        RoutingRule(task_profile=TaskProfile.CODE_GENERATION, model_name="nemotron-3-super"),
    ]
    return ModelRouter(endpoints=endpoints, rules=rules, default_model="gemini-2.5-flash")


def test_factory_accepts_output_key(config_dir, router):
    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(
        loader=loader,
        default_model="gemini-2.5-flash",
        model_router=router,
    )
    agent = factory.build(agent_name="orchestrator", output_key="orchestrator_result")
    assert agent.output_key == "orchestrator_result"


def test_factory_orchestrator_gets_string_model(config_dir, router):
    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(
        loader=loader,
        default_model="gemini-2.5-flash",
        model_router=router,
    )
    agent = factory.build(agent_name="orchestrator")
    assert agent.model == "gemini-2.5-flash"


def test_factory_dev_mgr_gets_litellm_instance(config_dir, router):
    from google.adk.models.lite_llm import LiteLlm

    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(
        loader=loader,
        default_model="gemini-2.5-flash",
        model_router=router,
    )
    agent = factory.build(agent_name="dev-mgr", soul_overlay="dev")
    assert isinstance(agent.model, LiteLlm)


def test_factory_explicit_model_overrides_router(config_dir, router):
    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(
        loader=loader,
        default_model="gemini-2.5-flash",
        model_router=router,
    )
    agent = factory.build(agent_name="dev-mgr", soul_overlay="dev", model="custom-model")
    assert agent.model == "custom-model"


def test_factory_no_router_uses_default(config_dir):
    loader = ConfigLoader(str(config_dir))
    factory = AgentFactory(
        loader=loader,
        default_model="gemini-2.5-flash",
        model_router=None,
    )
    agent = factory.build(agent_name="orchestrator")
    assert agent.model == "gemini-2.5-flash"
