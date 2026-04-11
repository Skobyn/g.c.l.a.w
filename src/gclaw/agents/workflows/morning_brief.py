"""Morning brief composed workflow — ParallelAgent fan-out + summary fold."""

from __future__ import annotations

from typing import Any

from google.adk.agents import LlmAgent, ParallelAgent, SequentialAgent


def build_morning_brief(
    *,
    workspace_tools: list[Any],
    dev_tools: list[Any],
    research_tools: list[Any],
    default_model: str = "gemini-2.5-flash",
) -> SequentialAgent:
    """Build the morning brief workflow.

    Three purpose-built 'workflow specialists' gather domain snapshots
    in parallel, each writing to a session state key. A summary agent
    folds them into a single prioritized rundown.
    """

    workspace_brief = LlmAgent(
        name="workspace_brief_specialist",
        model=default_model,
        description="Produces a workspace morning snapshot.",
        instruction=(
            "Produce a concise morning snapshot of the user's workspace:\n"
            "1. Call list_calendar_events_today to get today's meetings.\n"
            "2. Call list_unread_email with max_results=10 to get important unread email.\n"
            "3. Summarize in 3-5 bullets. Meetings first, then top email senders/subjects.\n"
            "Keep it scannable. No greetings, no sign-offs."
        ),
        tools=workspace_tools,
        output_key="workspace_summary",
    )

    dev_brief = LlmAgent(
        name="dev_brief_specialist",
        model=default_model,
        description="Produces a dev morning snapshot.",
        instruction=(
            "Produce a concise dev morning snapshot:\n"
            "1. Call list_open_prs to get open PRs.\n"
            "2. Call list_failing_workflows to get any failing CI runs.\n"
            "3. Summarize in 3-5 bullets. Blocking items first, then informational.\n"
            "Keep it scannable. No greetings."
        ),
        tools=dev_tools,
        output_key="dev_summary",
    )

    research_brief = LlmAgent(
        name="research_brief_specialist",
        model=default_model,
        description="Produces a research morning snapshot.",
        instruction=(
            "Produce a concise research morning snapshot:\n"
            "1. Call web_search with the user's tracked topics.\n"
            "2. Summarize the top 3 items in 3-5 bullets total.\n"
            "Keep it scannable."
        ),
        tools=research_tools,
        output_key="research_summary",
    )

    fan_out = ParallelAgent(
        name="MorningBriefFanOut",
        sub_agents=[workspace_brief, dev_brief, research_brief],
    )

    summary = LlmAgent(
        name="brief_summary_agent",
        model=default_model,
        description="Folds three domain snapshots into a single prioritized rundown.",
        instruction=(
            "You have three inputs in session state:\n"
            "- {workspace_summary}: calendar and email\n"
            "- {dev_summary}: PRs and CI\n"
            "- {research_summary}: articles and topics\n\n"
            "Fold into one morning brief. Lead with anything time-sensitive or blocking. "
            "Format: ## Workspace / ## Dev / ## Research — 3 bullets max per area. "
            "End with 'Today's focus:' recommending the single most important action."
        ),
        output_key="morning_brief",
    )

    return SequentialAgent(
        name="MorningBriefWorkflow",
        sub_agents=[fan_out, summary],
    )
