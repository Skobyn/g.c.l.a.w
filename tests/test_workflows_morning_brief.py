"""Tests for the morning brief composed workflow."""

import pytest
from google.adk.agents import LlmAgent, ParallelAgent, SequentialAgent

from gclaw.agents.workflows.morning_brief import build_morning_brief


def _dummy_tool():
    """A placeholder tool function."""
    return "dummy"


def test_morning_brief_is_a_sequential_agent():
    workflow = build_morning_brief(
        workspace_tools=[_dummy_tool],
        dev_tools=[_dummy_tool],
        research_tools=[_dummy_tool],
    )
    assert isinstance(workflow, SequentialAgent)
    assert workflow.name == "MorningBriefWorkflow"


def test_morning_brief_has_parallel_fan_out_and_summary():
    workflow = build_morning_brief(
        workspace_tools=[_dummy_tool],
        dev_tools=[_dummy_tool],
        research_tools=[_dummy_tool],
    )
    assert len(workflow.sub_agents) == 2

    fan_out, summary = workflow.sub_agents
    assert isinstance(fan_out, ParallelAgent)
    assert isinstance(summary, LlmAgent)
    assert summary.name == "brief_summary_agent"


def test_morning_brief_fan_out_has_three_specialists():
    workflow = build_morning_brief(
        workspace_tools=[_dummy_tool],
        dev_tools=[_dummy_tool],
        research_tools=[_dummy_tool],
    )
    fan_out = workflow.sub_agents[0]
    names = {sa.name for sa in fan_out.sub_agents}
    assert names == {
        "workspace_brief_specialist",
        "dev_brief_specialist",
        "research_brief_specialist",
    }


def test_specialists_have_correct_output_keys():
    workflow = build_morning_brief(
        workspace_tools=[_dummy_tool],
        dev_tools=[_dummy_tool],
        research_tools=[_dummy_tool],
    )
    fan_out = workflow.sub_agents[0]
    output_keys = {sa.output_key for sa in fan_out.sub_agents}
    assert output_keys == {
        "workspace_summary",
        "dev_summary",
        "research_summary",
    }


def test_summary_agent_has_morning_brief_output_key():
    workflow = build_morning_brief(
        workspace_tools=[_dummy_tool],
        dev_tools=[_dummy_tool],
        research_tools=[_dummy_tool],
    )
    summary = workflow.sub_agents[1]
    assert summary.output_key == "morning_brief"


def test_specialists_bind_their_tools():
    def workspace_tool():
        return "ws"

    def dev_tool():
        return "dv"

    def research_tool():
        return "rs"

    workflow = build_morning_brief(
        workspace_tools=[workspace_tool],
        dev_tools=[dev_tool],
        research_tools=[research_tool],
    )
    fan_out = workflow.sub_agents[0]
    by_name = {sa.name: sa for sa in fan_out.sub_agents}

    assert workspace_tool in by_name["workspace_brief_specialist"].tools
    assert dev_tool in by_name["dev_brief_specialist"].tools
    assert research_tool in by_name["research_brief_specialist"].tools
    assert dev_tool not in by_name["workspace_brief_specialist"].tools
    assert workspace_tool not in by_name["dev_brief_specialist"].tools
