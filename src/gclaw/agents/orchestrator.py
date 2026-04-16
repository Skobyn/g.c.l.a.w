"""Root orchestrator agent with AgentTool-wrapped managers and workflows."""

from __future__ import annotations

import logging
from typing import Any, Callable, TYPE_CHECKING

from google.adk.agents import LlmAgent
from google.adk.tools import agent_tool
from google.genai import types as genai_types

from gclaw.agents.factory import AgentFactory
from gclaw.agents.workflows.morning_brief import build_morning_brief
from gclaw.agents.workflows.commit_message import build_commit_message_workflow
from gclaw.board.service import BoardService
from gclaw.models.task import TaskStatus
from gclaw.routing.router import ModelRouter
from gclaw.tools import (
    comms_tools,
    context_tools,
    dev_tools,
    home_tools,
    postiz_tools,
    research_tools,
    workspace_tools,
)

if TYPE_CHECKING:
    from gclaw.memory.service import MemoryService

logger = logging.getLogger(__name__)


# ---------- Board function tools ----------


def create_board_task_tool(board_service: BoardService) -> Callable:
    def create_board_task(
        title: str,
        assignee: str,
        description: str = "",
        priority: str = "medium",
        source_origin: str = "orchestrator",
    ) -> str:
        """Create an async task on the project board for a manager to pick up later.

        Args:
            title: Short description of what needs to be done.
            assignee: Which manager should handle this.
                One of: workspace-mgr, dev-mgr, home-mgr, comms-mgr, research-mgr.
            description: Detailed context for the assigned agent.
            priority: Task priority — high, medium, or low.
            source_origin: Which agent created this task.

        Returns:
            Confirmation with the created task ID and details.
        """
        task = board_service.create_task(
            title=title,
            assignee=assignee,
            description=description,
            priority=priority,
            source_type="agent",
            source_origin=source_origin,
            status=TaskStatus.QUEUED,
        )
        return (
            f"Task created: [{task.id}] '{task.title}' "
            f"assigned to {task.assignee} (priority: {task.priority})"
        )

    return create_board_task


def list_board_tasks_tool(board_service: BoardService) -> Callable:
    def list_board_tasks() -> str:
        """List all tasks currently on the project board.

        Returns:
            A formatted list of all board tasks with their status.
        """
        tasks = board_service.get_all_tasks()
        if not tasks:
            return "The board is empty — no tasks."
        lines = []
        for t in tasks:
            lines.append(
                f"- [{t.id}] {t.title} | status: {t.status} | "
                f"assignee: {t.assignee} | priority: {t.priority}"
            )
        return "\n".join(lines)

    return list_board_tasks


def get_board_task_tool(board_service: BoardService) -> Callable:
    def get_board_task(task_id: str) -> str:
        """Get details of a specific board task by ID.

        Args:
            task_id: The task ID to look up.

        Returns:
            Full task details or a not-found message.
        """
        task = board_service._repo.get(task_id)
        if task is None:
            return f"Task {task_id} not found."
        parts = [
            f"Task: {task.title}",
            f"ID: {task.id}",
            f"Status: {task.status}",
            f"Assignee: {task.assignee}",
            f"Priority: {task.priority}",
            f"Description: {task.description or '(none)'}",
            f"Source: {task.source.type} / {task.source.origin or 'user'}",
            f"Dependencies: {task.dependencies or '(none)'}",
            f"Requires approval: {task.requires_approval}",
        ]
        if task.result:
            parts.append(f"Result: {task.result.summary}")
        return "\n".join(parts)

    return get_board_task


def complete_board_task_tool(board_service: BoardService) -> Callable:
    def complete_board_task(task_id: str, summary: str = "") -> str:
        """Mark a board task as complete.

        Args:
            task_id: The task ID to complete.
            summary: Brief summary of what was done.

        Returns:
            Confirmation message.
        """
        task = board_service.complete(task_id=task_id, summary=summary)
        if task is None:
            return f"Task {task_id} not found."
        return f"Task [{task.id}] '{task.title}' marked as DONE."

    return complete_board_task


# ---------- Manager builders ----------


def _make_memory_recall_callback(
    memory_service: "MemoryService", agent_id: str
) -> Callable:
    """Build a before_agent_callback that recalls agent-scoped memories.

    When the manager is invoked (via AgentTool from the orchestrator),
    this callback fires before the manager's LLM call. It looks up the
    user's memories scoped to this specific agent_id and injects them
    as additional user-role context. The orchestrator-scoped recall at
    `AgentRunner.run` handles the outer layer; this callback handles
    the per-manager inner layer so each manager builds up its own
    memory over time (e.g. comms-mgr remembers communication style
    separately from dev-mgr's preferred code-review tone).

    Failures are logged and suppressed — agent-scoped recall must never
    break a manager turn.
    """

    async def before(callback_context: Any) -> Any:
        # ADK's BaseAgent enforces that the callback parameter is literally
        # named `callback_context` — it's called as a kwarg, not positional.
        # See google/adk/agents/base_agent.py:146.
        user_id = getattr(callback_context, "user_id", None)
        user_content = getattr(callback_context, "user_content", None)
        if not user_id or user_content is None:
            return None

        query = ""
        parts = getattr(user_content, "parts", None) or []
        for part in parts:
            text = getattr(part, "text", None)
            if text:
                query = text
                break
        if not query:
            return None

        try:
            memories = await memory_service.recall(
                user_id=user_id,
                query=query,
                agent_id=agent_id,
                merge_user_scope=False,
            )
        except Exception:
            logger.warning(
                "agent-scoped recall failed for %s", agent_id, exc_info=True
            )
            return None

        if not memories:
            return None

        formatted = memory_service.format_for_prompt(memories)
        return genai_types.Content(
            role="user",
            parts=[
                genai_types.Part(
                    text=f"[Agent memories for {agent_id}]\n{formatted}"
                )
            ],
        )

    return before


def build_managers(
    factory: AgentFactory,
    board_tools: list,
    memory_service: "MemoryService | None" = None,
) -> dict[str, LlmAgent]:
    """Build the five manager agents as thin routers.

    Each manager is bound to its own domain tools plus the shared board tools
    (so it can create follow-up async tasks for work it cannot finish now).

    If `memory_service` is provided, each manager also receives a
    `before_agent_callback` that auto-recalls agent-scoped memories before
    the manager's LLM call fires.
    """
    ctx_tools = [
        context_tools.context_write,
        context_tools.context_read_latest,
        context_tools.context_list,
        context_tools.context_write_image,
    ]

    ws_tools = [
        workspace_tools.list_unread_email,
        workspace_tools.send_email,
        workspace_tools.list_calendar_events_today,
        workspace_tools.create_calendar_event,
        workspace_tools.list_drive_files,
        workspace_tools.read_drive_doc,
    ] + board_tools + ctx_tools

    dv_tools = [
        dev_tools.list_open_prs,
        dev_tools.get_pr_diff,
        dev_tools.list_failing_workflows,
        dev_tools.create_issue,
        dev_tools.get_current_diff,
        dev_tools.read_local_file,
    ] + board_tools + ctx_tools

    hm_tools = [
        home_tools.list_devices,
        home_tools.set_device_state,
    ] + board_tools + ctx_tools

    pz_tools = [
        postiz_tools.postiz_upload_image,
        postiz_tools.postiz_upload_image_b64,
        postiz_tools.postiz_create_draft,
        postiz_tools.postiz_register_images,
        postiz_tools.postiz_list_channels,
    ]

    cm_tools = [
        comms_tools.list_chat_spaces,
        comms_tools.post_chat_message,
    ] + pz_tools + board_tools + ctx_tools

    rs_tools = [
        research_tools.web_search,
        research_tools.fetch_url,
    ] + board_tools + ctx_tools

    def _recall_cb(agent_id: str) -> Any:
        if memory_service is None:
            return None
        return _make_memory_recall_callback(memory_service, agent_id)

    return {
        "workspace_mgr": factory.build(
            agent_name="workspace-mgr",
            soul_overlay="workspace",
            tools=ws_tools,
            description=(
                "Routes workspace requests (Gmail, Calendar, Drive, Docs) "
                "to the single best tool. Router — does not synthesize."
            ),
            before_agent_callback=_recall_cb("workspace-mgr"),
        ),
        "dev_mgr": factory.build(
            agent_name="dev-mgr",
            soul_overlay="dev",
            tools=dv_tools,
            description=(
                "Routes dev requests (GitHub, code, local repo) to the "
                "single best tool. Router — does not synthesize."
            ),
            before_agent_callback=_recall_cb("dev-mgr"),
        ),
        "home_mgr": factory.build(
            agent_name="home-mgr",
            soul_overlay="home",
            tools=hm_tools,
            description=(
                "Routes smart home requests to the single best tool. "
                "Router — does not synthesize."
            ),
            before_agent_callback=_recall_cb("home-mgr"),
        ),
        "comms_mgr": factory.build(
            agent_name="comms-mgr",
            soul_overlay="comms",
            tools=cm_tools,
            description=(
                "Routes inter-platform comms (Google Chat) to the single "
                "best tool. Router — does not synthesize."
            ),
            before_agent_callback=_recall_cb("comms-mgr"),
        ),
        "research_mgr": factory.build(
            agent_name="research-mgr",
            soul_overlay="research",
            tools=rs_tools,
            description=(
                "Routes research requests (web search, URL fetch) to the "
                "single best tool. Router — does not synthesize."
            ),
            before_agent_callback=_recall_cb("research-mgr"),
        ),
    }


# ---------- Orchestrator builder ----------


def build_orchestrator(
    factory: AgentFactory,
    board_service: BoardService,
    router: ModelRouter | None = None,
    default_model: str = "gemini-2.5-flash",
    memories: list[str] | None = None,
    memory_service: "MemoryService | None" = None,
) -> LlmAgent:
    """Build the root orchestrator with AgentTool-wrapped managers and workflows.

    Args:
        factory: the AgentFactory used to build named agents from config files.
        board_service: the board service used to create/list/get/complete tasks.
        router: the ModelRouter — needed by workflows that construct raw LlmAgents.
        default_model: fallback model ID used when the router is absent.
        memories: optional memory facts to prepend to the system prompt.
        memory_service: when provided, each manager gets a
            `before_agent_callback` that recalls agent-scoped memories.

    Returns:
        The root orchestrator LlmAgent, wired with all managers and workflows
        as AgentTools plus the board function tools. Never uses `sub_agents=`.
    """
    board_tools = [
        create_board_task_tool(board_service),
        list_board_tasks_tool(board_service),
        get_board_task_tool(board_service),
        complete_board_task_tool(board_service),
    ]

    managers = build_managers(
        factory, board_tools, memory_service=memory_service
    )

    morning_brief = build_morning_brief(
        workspace_tools=[
            workspace_tools.list_unread_email,
            workspace_tools.list_calendar_events_today,
        ],
        dev_tools=[
            dev_tools.list_open_prs,
            dev_tools.list_failing_workflows,
        ],
        research_tools=[research_tools.web_search],
        default_model=default_model,
    )

    commit_msg = build_commit_message_workflow(
        dev_tools=[
            dev_tools.get_current_diff,
            dev_tools.read_local_file,
        ],
        router=router,
        default_model=default_model,
    )

    orchestrator_tools: list[Any] = [
        agent_tool.AgentTool(agent=managers["workspace_mgr"]),
        agent_tool.AgentTool(agent=managers["dev_mgr"]),
        agent_tool.AgentTool(agent=managers["home_mgr"]),
        agent_tool.AgentTool(agent=managers["comms_mgr"]),
        agent_tool.AgentTool(agent=managers["research_mgr"]),
        agent_tool.AgentTool(agent=morning_brief),
        agent_tool.AgentTool(agent=commit_msg),
        *board_tools,
    ]

    return factory.build(
        agent_name="orchestrator",
        tools=orchestrator_tools,
        memories=memories,
        description=(
            "Root orchestrator. Classifies user intent and delegates to the "
            "right manager or composed workflow. Never does work directly."
        ),
    )
