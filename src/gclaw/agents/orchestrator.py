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
    agent_architect_tools,
    comms_tools,
    context_tools,
    image_gen_tools,
    dev_tools,
    home_tools,
    postiz_tools,
    research_tools,
    user_profile_tools,
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
                One of: workspace-mgr, dev-mgr, home-mgr, comms-mgr,
                research-mgr, content-mgr.
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
    def get_board_task(
        task_id: str,
        tool_context: Any = None,
    ) -> str:
        """Get details of a specific board task by ID.

        Side effect: if the task is currently QUEUED, this call
        auto-transitions it to IN_PROGRESS and emits a
        ``task.picked_up`` event. This is how the orchestrator's 4-step
        HIGH-priority lifecycle surfaces a "started" bubble in the chat
        UI under the delegating turn, and how a manager agent reading a
        newly-assigned task signals "I'm about to work on this" without
        an explicit pick-up tool call.

        Earlier iterations gated the auto-pickup on
        ``caller_agent == task.assignee`` (PR #31) to prevent accidental
        orphans from the orchestrator inspecting the board. That
        broke the 4-step HIGH flow — orchestrator never matches
        assignee, so ``get_board_task`` became a no-op and no
        ``task.picked_up`` event ever fired. The real prevention for
        the accident it was worried about now lives on
        ``complete_board_task``'s assignee gate (added in the same PR
        that reverted this one): smuggling a task to DONE without a
        proper pickup is blocked, which is the only harm that actually
        mattered.

        Args:
            task_id: The task ID to look up.
            tool_context: Unused (kept for signature stability with the
                older gated version).

        Returns:
            Full task details or a not-found message.
        """
        from gclaw.models.task import TaskStatus

        task = board_service._repo.get(task_id)
        if task is None:
            return f"Task {task_id} not found."
        # Unconditional auto-pickup on first read of a QUEUED task.
        # pick_up itself re-reads, transitions, and emits; swallowing
        # failures keeps the read path intact if the task moved between
        # the read above and the transition below.
        if task.status == TaskStatus.QUEUED:
            try:
                task = board_service.pick_up(task_id)
            except Exception:
                pass
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
    def complete_board_task(
        task_id: str,
        summary: str = "",
        tool_context: Any = None,
    ) -> str:
        """Mark a board task as complete.

        Refuses to complete:
          * Tasks already in terminal FAILED state (use a fresh task
            for a retry — don't paper over the failure).
          * Tasks where the summary signals failure ("FAILED:",
            "ERROR:", "could not"). Failed work goes through
            ``fail_board_task``, not a DONE with a sad summary.

        Transparently transitions a QUEUED task through IN_PROGRESS first
        when the caller is the task's assignee. Heartbeat-driven manager
        runs would otherwise hit ``ValueError: cannot transition
        QUEUED → DONE`` and the task would stay QUEUED forever.

        Args:
            task_id: The task ID to complete.
            summary: Brief summary of what was done. Must describe
                actual work performed — not a failure message.
            tool_context: Injected by ADK; used to read ``agent_name``
                for the assignee-auto-pickup gate.

        Returns:
            Confirmation message, or a refusal explaining why.
        """
        from gclaw.models.task import TaskStatus

        current = board_service._repo.get(task_id)
        if current is None:
            return f"Task {task_id} not found."
        if current.status == TaskStatus.FAILED:
            return (
                f"Task [{task_id}] is already FAILED — refusing to mark "
                "it DONE. If new work succeeded, create a fresh task; "
                "if it really did succeed on retry, that's a separate "
                "create_board_task → complete_board_task lifecycle."
            )
        if current.status == TaskStatus.DONE:
            return f"Task [{task_id}] is already DONE — no-op."

        # Reject summaries that look like a failure rationale. The
        # orchestrator was hallucinating "completions" for tasks the
        # manager never actually finished, with a "FAILED: ..." text
        # body. Force those into fail_board_task instead.
        normalized = (summary or "").strip().lower()
        failure_markers = (
            "failed:", "failed.", "failed —", "error:", "could not",
            "unable to", "task abandoned", "research tool interrupted",
        )
        if any(m in normalized[:120] for m in failure_markers):
            return (
                f"Refusing to mark [{task_id}] DONE with a failure "
                f"summary. Call fail_board_task(task_id, reason) "
                f"instead — DONE means real work shipped."
            )

        if current.status == TaskStatus.QUEUED:
            caller = (
                getattr(tool_context, "agent_name", None)
                if tool_context is not None
                else None
            )
            caller_norm = (caller or "").replace("_", "-")
            if caller_norm and caller_norm == current.assignee:
                try:
                    board_service.pick_up(task_id)
                except Exception:
                    # Fall through — let the real transition raise so the
                    # LLM sees a meaningful error instead of a silent
                    # skip.
                    pass
        task = board_service.complete(task_id=task_id, summary=summary)
        if task is None:
            return f"Task {task_id} not found."
        return f"Task [{task.id}] '{task.title}' marked as DONE."

    return complete_board_task


def fail_board_task_tool(board_service: BoardService) -> Callable:
    def fail_board_task(
        task_id: str,
        reason: str,
        tool_context: Any = None,
    ) -> str:
        """Mark a board task as FAILED with a reason.

        Use this when work cannot be completed (tool error, missing
        capability, dependency unavailable, manager unstable). The
        heartbeat instructions tell managers to call this rather than
        completing the task with a "FAILED:" summary — failures need
        to be visible in the FAILED column, not buried in DONE.

        Args:
            task_id: The task ID to fail.
            reason: Short explanation of why it can't be done. Will
                be shown verbatim in the failed-task tooltip + the
                board card's rejection note.
            tool_context: Injected by ADK; unused today, kept for
                signature stability with the rest of the board tools.

        Returns:
            Confirmation or a not-found message.
        """
        from gclaw.models.task import TaskStatus

        current = board_service._repo.get(task_id)
        if current is None:
            return f"Task {task_id} not found."
        if current.status == TaskStatus.FAILED:
            return f"Task [{task_id}] already FAILED — no-op."
        if current.status == TaskStatus.DONE:
            return (
                f"Task [{task_id}] is already DONE — refusing to mark "
                "it FAILED retroactively."
            )
        try:
            task = board_service.fail(task_id=task_id, reason=reason)
        except ValueError as e:
            return f"fail_board_task refused: {e}"
        return f"Task [{task.id}] '{task.title}' marked as FAILED: {reason[:200]}"

    return fail_board_task


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

    img_tools = [
        image_gen_tools.generate_image,
        image_gen_tools.generate_image_b64,
    ]

    cm_tools = [
        comms_tools.list_chat_spaces,
        comms_tools.post_chat_message,
    ] + board_tools + ctx_tools

    ct_tools = pz_tools + img_tools + board_tools + ctx_tools

    rs_tools = [
        research_tools.web_search,
        research_tools.fetch_url,
    ] + board_tools + ctx_tools

    pf_tools = [
        user_profile_tools.read_user_profile,
        user_profile_tools.update_user_profile,
    ] + ctx_tools

    aa_tools = [
        agent_architect_tools.read_agent_file,
        agent_architect_tools.read_soul_file,
        agent_architect_tools.list_agent_files,
        agent_architect_tools.list_registered_agents,
        agent_architect_tools.write_agent_file,
        agent_architect_tools.write_soul_file,
        agent_architect_tools.register_standalone_agent,
        agent_architect_tools.update_agent_model,
        # ADR-0006: eval feedback loop. Architect drafts a starter
        # evalset and runs it against an ephemeral build of the draft
        # before asking the user to approve registration.
        agent_architect_tools.generate_starter_evalset,
        agent_architect_tools.run_eval_against_draft,
    ] + board_tools + ctx_tools

    def _recall_cb(agent_id: str) -> Any:
        if memory_service is None:
            return None
        return _make_memory_recall_callback(memory_service, agent_id)

    # Manager spec list — (dict_key, agent_name, soul_overlay, tools, description).
    # Optional managers (required=False) are skipped with a log warning if
    # their agent definition file is missing. This lets forks/overlays drop
    # managers they don't use without patching orchestrator.py — e.g. a
    # non-Apex fork can remove agents/content-apex.md and the orchestrator
    # boots without it.
    specs: list[tuple] = [
        ("workspace_mgr", "workspace-mgr", "workspace", ws_tools,
         "Routes workspace requests (Gmail, Calendar, Drive, Docs) to the "
         "single best tool. Router — does not synthesize.", True),
        ("dev_mgr", "dev-mgr", "dev", dv_tools,
         "Routes dev requests (GitHub, code, local repo) to the single "
         "best tool. Router — does not synthesize.", True),
        ("home_mgr", "home-mgr", "home", hm_tools,
         "Routes smart home requests to the single best tool. Router — "
         "does not synthesize.", True),
        ("comms_mgr", "comms-mgr", "comms", cm_tools,
         "Routes inter-platform comms (Google Chat) to the single best "
         "tool. Router — does not synthesize.", True),
        ("research_mgr", "research-mgr", "research", rs_tools,
         "Routes research requests (web search, URL fetch) to the single "
         "best tool. Router — does not synthesize.", True),
        ("profile_mgr", "profile-mgr", "profile", pf_tools,
         "Owns user.md. Runs onboarding when the profile is blank, "
         "updates it when the user reveals stable new facts, and answers "
         "'what do you know about me?' questions. Always confirms with "
         "the user before writing.", True),
        ("content_mgr", "content-mgr", "content", ct_tools,
         "Generic content pipeline — fallback when the brand channel is "
         "ambiguous. Prefer content-scott or content-apex when the brand "
         "is known.", False),
        ("content_scott", "content-scott", "content-scott", ct_tools,
         "Runs the social-content pipeline for the Scott personal-brand "
         "channel. Pins POSTIZ_CHANNEL_PRIMARY; never posts to the Apex "
         "channel.", False),
        ("content_apex", "content-apex", "content-apex", ct_tools,
         "Runs the social-content pipeline for the Apex brand channel. "
         "Pins POSTIZ_CHANNEL_SECONDARY; never posts to the Scott "
         "channel.", False),
        ("agent_architect", "agent-architect", "agent-architect", aa_tools,
         "Designs and registers new agents in-process. Use when the "
         "user asks to build/create a new specialist or manager. "
         "Stages drafts, requires explicit approval before registration.",
         False),
    ]

    managers: dict[str, Any] = {}
    for key, agent_name, overlay, tools, desc, required in specs:
        try:
            managers[key] = factory.build(
                agent_name=agent_name,
                soul_overlay=overlay,
                tools=tools,
                description=desc,
                before_agent_callback=_recall_cb(agent_name),
            )
        except FileNotFoundError:
            if required:
                raise
            import logging as _lg
            _lg.getLogger(__name__).info(
                "build_managers: skipping optional manager %s "
                "(no agent file at agents/%s.md)",
                key, agent_name,
            )
    return managers


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
        fail_board_task_tool(board_service),
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
        agent_tool.AgentTool(agent=managers["profile_mgr"]),
    ]
    for optional_key in (
        "content_mgr",
        "content_scott",
        "content_apex",
        "agent_architect",
    ):
        if optional_key in managers:
            orchestrator_tools.append(
                agent_tool.AgentTool(agent=managers[optional_key])
            )
    orchestrator_tools.extend([
        agent_tool.AgentTool(agent=morning_brief),
        agent_tool.AgentTool(agent=commit_msg),
        user_profile_tools.read_user_profile,
        *board_tools,
    ])

    return factory.build(
        agent_name="orchestrator",
        tools=orchestrator_tools,
        memories=memories,
        description=(
            "Root orchestrator. Classifies user intent and delegates to the "
            "right manager or composed workflow. Never does work directly."
        ),
    )
