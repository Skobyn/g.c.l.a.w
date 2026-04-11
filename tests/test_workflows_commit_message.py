"""Tests for the commit message composed workflow."""

import pytest
from google.adk.agents import LlmAgent, SequentialAgent

from gclaw.agents.workflows.commit_message import build_commit_message_workflow
from gclaw.agents.workflows.validators import ValidateCommitMsg
from gclaw.models.model_config import ModelEndpoint, RoutingRule, TaskProfile
from gclaw.routing.router import ModelRouter


def _dummy_tool():
    return "dummy"


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
        RoutingRule(task_profile=TaskProfile.CODE_GENERATION, model_name="nemotron-3-super"),
    ]
    return ModelRouter(endpoints=endpoints, rules=rules, default_model="gemini-2.5-flash")


def test_commit_workflow_is_a_sequential_agent(router):
    workflow = build_commit_message_workflow(
        dev_tools=[_dummy_tool],
        router=router,
        default_model="gemini-2.5-flash",
    )
    assert isinstance(workflow, SequentialAgent)
    assert workflow.name == "CommitMessageWorkflow"


def test_commit_workflow_has_three_steps(router):
    workflow = build_commit_message_workflow(
        dev_tools=[_dummy_tool],
        router=router,
        default_model="gemini-2.5-flash",
    )
    assert len(workflow.sub_agents) == 3

    draft, reviewer, validate = workflow.sub_agents
    assert isinstance(draft, LlmAgent)
    assert draft.name == "commit_draft_specialist"
    assert draft.output_key == "commit_draft"

    assert isinstance(reviewer, LlmAgent)
    assert reviewer.name == "style_reviewer_specialist"
    assert reviewer.output_key == "review_status"

    assert isinstance(validate, ValidateCommitMsg)


def test_draft_specialist_uses_code_generation_model_via_litellm(router):
    from google.adk.models.lite_llm import LiteLlm

    workflow = build_commit_message_workflow(
        dev_tools=[_dummy_tool],
        router=router,
        default_model="gemini-2.5-flash",
    )
    draft = workflow.sub_agents[0]
    assert isinstance(draft.model, LiteLlm)


def test_commit_workflow_no_router_falls_back_to_default():
    workflow = build_commit_message_workflow(
        dev_tools=[_dummy_tool],
        router=None,
        default_model="gemini-2.5-flash",
    )
    draft = workflow.sub_agents[0]
    assert draft.model == "gemini-2.5-flash"


def test_draft_specialist_receives_dev_tools(router):
    tool_a = lambda: "a"
    tool_b = lambda: "b"
    workflow = build_commit_message_workflow(
        dev_tools=[tool_a, tool_b],
        router=router,
        default_model="gemini-2.5-flash",
    )
    draft = workflow.sub_agents[0]
    assert tool_a in draft.tools
    assert tool_b in draft.tools
