"""Golden eval cases for the GClaw orchestrator.

Each case states a user query and the tool names the orchestrator
should call. A case passes if *any* of its `expected_tools` shows up
in the actual `tool_calls` list from `AgentRunner.run`. This is
deliberately permissive — we want to catch routing regressions, not
enforce a single "correct" tool selection.

Tool names are the exact strings ADK emits in `function_call.name`:

- Manager names come from `AgentFactory.build`'s safe_name (hyphens
  → underscores), so `workspace-mgr` becomes `workspace_mgr` etc.
- Workflow names come from the `name=` kwarg on the SequentialAgent
  wrapping each workflow — `MorningBriefWorkflow`, `CommitMessageWorkflow`.
- Board function tools are the Python function names declared in
  `orchestrator.create_board_task_tool` and friends:
  `create_board_task`, `list_board_tasks`, `get_board_task`,
  `complete_board_task`.

The `GOLDEN_CASES` list is intentionally small (~12 cases). Its job
is to be the seed of a growing eval suite, not an exhaustive
regression fence. Add cases as behaviour surfaces.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvalCase:
    """One golden evaluation case.

    Attributes:
        query: The user message sent to the orchestrator.
        expected_tools: Tool names that should appear in the
            orchestrator's tool_calls. A case passes if *any* of
            these are called. An empty list means "the orchestrator
            should respond conversationally, no tool call expected".
        description: One-sentence human label for reports.
        category: Grouping label — "routing", "workflow", "board",
            or "conversational".
    """

    query: str
    expected_tools: list[str]
    description: str
    category: str


GOLDEN_CASES: list[EvalCase] = [
    # --- Routing: each manager should be hit by at least one case -----------
    EvalCase(
        query="Draft a reply to the last email from my boss saying I'll be there.",
        expected_tools=["workspace_mgr", "comms_mgr", "create_board_task"],
        description="email drafting → workspace/comms manager or queued as task",
        category="routing",
    ),
    EvalCase(
        query="What PRs are open on the apex-internal-apps repo right now?",
        expected_tools=["dev_mgr"],
        description="GitHub PR lookup → dev manager",
        category="routing",
    ),
    EvalCase(
        query="Turn off the kitchen lights and set the thermostat to 68.",
        expected_tools=["home_mgr"],
        description="smart home command → home manager",
        category="routing",
    ),
    EvalCase(
        query="Post an update to the #engineering Chat space that the deploy is done.",
        expected_tools=["comms_mgr", "create_board_task"],
        description="Chat posting → comms manager or queued as task",
        category="routing",
    ),
    EvalCase(
        query="Research the latest Gemini 3 context window limits and summarise.",
        expected_tools=["research_mgr", "create_board_task"],
        description="web research → research manager or queued as task",
        category="routing",
    ),
    # --- Workflows: composed SequentialAgents ------------------------------
    EvalCase(
        query="Give me my morning brief.",
        expected_tools=["MorningBriefWorkflow"],
        description="morning brief → composed workflow",
        category="workflow",
    ),
    EvalCase(
        query="Write me a commit message for the changes I've staged.",
        expected_tools=["CommitMessageWorkflow"],
        description="commit message → composed workflow",
        category="workflow",
    ),
    # --- Board function tools ----------------------------------------------
    EvalCase(
        query="Create a task to review PR 42 and assign it to dev-mgr.",
        expected_tools=["create_board_task"],
        description="task creation → board function tool",
        category="board",
    ),
    EvalCase(
        query="What's on my board right now?",
        expected_tools=["list_board_tasks"],
        description="board listing → board function tool",
        category="board",
    ),
    EvalCase(
        query="Mark task t7 as done.",
        expected_tools=["complete_board_task"],
        description="task completion → board function tool",
        category="board",
    ),
    # --- Conversational: no tool call expected -----------------------------
    EvalCase(
        query="Hello! How are you today?",
        expected_tools=[],
        description="small talk → conversational, no tools",
        category="conversational",
    ),
    EvalCase(
        query="Thanks, that's all for now.",
        expected_tools=[],
        description="goodbye → conversational, no tools",
        category="conversational",
    ),
]
