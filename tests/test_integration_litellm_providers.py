"""Integration test: non-Gemini providers flow through LiteLlm.

This verifies the factory + router + orchestrator wiring correctly produces
LiteLlm-wrapped agents for non-Gemini providers (e.g. Nemotron via OpenRouter),
replacing the now-retired RemoteRunner side-channel.
"""

from unittest.mock import MagicMock

import pytest
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import agent_tool

from gclaw.agents.factory import AgentFactory
from gclaw.agents.orchestrator import build_orchestrator
from gclaw.board.service import BoardService
from gclaw.config.loader import ConfigLoader
from gclaw.models.model_config import ModelEndpoint, RoutingRule, TaskProfile
from gclaw.routing.router import ModelRouter


@pytest.fixture
def tmp_config_dir(tmp_path):
    soul = tmp_path / "soul"
    soul.mkdir()
    (soul / "base.md").write_text("base\n")
    for name in ("workspace", "dev", "home", "comms", "research", "profile", "content"):
        (soul / f"{name}.md").write_text(f"{name} overlay\n")

    agents = tmp_path / "agents"
    agents.mkdir()
    for name in (
        "orchestrator",
        "workspace-mgr",
        "dev-mgr",
        "home-mgr",
        "comms-mgr",
        "research-mgr",
        "profile-mgr",
        "content-mgr",
    ):
        (agents / f"{name}.md").write_text(f"{name} role\n")

    return tmp_path


@pytest.fixture
def full_router():
    endpoints = {
        "gemini-flash": ModelEndpoint(
            name="gemini-flash",
            endpoint_id="gemini-2.5-flash",
            provider="gemini",
            max_context_tokens=1_000_000,
        ),
        "nemotron-3-super": ModelEndpoint(
            name="nemotron-3-super",
            endpoint_id="nvidia/nemotron-3-super-120b-a12b:free",
            provider="openrouter",
            max_context_tokens=1_000_000,
        ),
    }
    rules = [
        RoutingRule(task_profile=TaskProfile.ORCHESTRATION, model_name="gemini-flash"),
        RoutingRule(task_profile=TaskProfile.SUMMARIZATION, model_name="gemini-flash"),
        RoutingRule(task_profile=TaskProfile.PERSONALITY, model_name="gemini-flash"),
        RoutingRule(task_profile=TaskProfile.CODE_GENERATION, model_name="nemotron-3-super"),
        RoutingRule(task_profile=TaskProfile.TOOL_EXECUTION, model_name="nemotron-3-super"),
    ]
    return ModelRouter(
        endpoints=endpoints, rules=rules, default_model="gemini-2.5-flash"
    )


def test_orchestrator_uses_gemini_flash_string(tmp_config_dir, full_router):
    loader = ConfigLoader(str(tmp_config_dir))
    factory = AgentFactory(
        loader=loader, default_model="gemini-2.5-flash", model_router=full_router
    )
    bs = MagicMock(spec=BoardService)
    orch = build_orchestrator(
        factory=factory,
        board_service=bs,
        router=full_router,
        default_model="gemini-2.5-flash",
    )
    assert orch.model == "gemini-2.5-flash"


def test_dev_mgr_uses_litellm_instance(tmp_config_dir, full_router):
    loader = ConfigLoader(str(tmp_config_dir))
    factory = AgentFactory(
        loader=loader, default_model="gemini-2.5-flash", model_router=full_router
    )
    bs = MagicMock(spec=BoardService)
    orch = build_orchestrator(
        factory=factory,
        board_service=bs,
        router=full_router,
        default_model="gemini-2.5-flash",
    )

    dev_mgr = None
    for tool in orch.tools:
        if isinstance(tool, agent_tool.AgentTool) and tool.agent.name == "dev_mgr":
            dev_mgr = tool.agent
            break

    assert dev_mgr is not None, "dev_mgr not found in orchestrator tools"
    assert isinstance(dev_mgr.model, LiteLlm), (
        f"dev_mgr.model should be LiteLlm, got {type(dev_mgr.model).__name__}"
    )


def test_commit_draft_specialist_uses_litellm(tmp_config_dir, full_router):
    loader = ConfigLoader(str(tmp_config_dir))
    factory = AgentFactory(
        loader=loader, default_model="gemini-2.5-flash", model_router=full_router
    )
    bs = MagicMock(spec=BoardService)
    orch = build_orchestrator(
        factory=factory,
        board_service=bs,
        router=full_router,
        default_model="gemini-2.5-flash",
    )

    commit_wf = None
    for tool in orch.tools:
        if isinstance(tool, agent_tool.AgentTool) and tool.agent.name == "CommitMessageWorkflow":
            commit_wf = tool.agent
            break
    assert commit_wf is not None

    draft_specialist = commit_wf.sub_agents[0]
    assert draft_specialist.name == "commit_draft_specialist"
    assert isinstance(draft_specialist.model, LiteLlm)


def test_workspace_mgr_uses_gemini_string(tmp_config_dir, full_router):
    loader = ConfigLoader(str(tmp_config_dir))
    factory = AgentFactory(
        loader=loader, default_model="gemini-2.5-flash", model_router=full_router
    )
    bs = MagicMock(spec=BoardService)
    orch = build_orchestrator(
        factory=factory,
        board_service=bs,
        router=full_router,
        default_model="gemini-2.5-flash",
    )

    workspace_mgr = None
    for tool in orch.tools:
        if isinstance(tool, agent_tool.AgentTool) and tool.agent.name == "workspace_mgr":
            workspace_mgr = tool.agent
            break

    assert workspace_mgr is not None
    # workspace-mgr routes to SUMMARIZATION → gemini-flash → bare string
    assert isinstance(workspace_mgr.model, str)
