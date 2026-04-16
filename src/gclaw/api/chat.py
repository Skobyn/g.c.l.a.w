"""Chat endpoint.

Supports an optional ``agent_name`` so the user can talk directly to
any registered agent (orchestrator, a manager, a specialist). When
omitted the request routes to the default (orchestrator) runner and
behaves exactly as the pre-switcher chat endpoint did.

Session scoping: every non-default agent gets its own per-session
namespace by appending the agent name to the session id the client
passes. That keeps ADK's session state — which is keyed on session_id
— from leaking turns across agents. The default/orchestrator path
uses the raw session_id so existing clients and session stores keep
working unchanged.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from gclaw.auth.dependencies import get_current_user_id
from gclaw.dispatch.runner import AgentRunner
from gclaw.dispatch.runner_registry import AgentRunnerRegistry

router = APIRouter()

_runner: AgentRunner | None = None
_registry: AgentRunnerRegistry | None = None


def init_chat_router(
    runner_or_registry: AgentRunner | AgentRunnerRegistry,
) -> APIRouter:
    """Initialise the chat router.

    Accepts either an ``AgentRunner`` (legacy single-agent wiring) or an
    ``AgentRunnerRegistry`` (multi-agent switcher). When a runner is
    passed we wrap it in a single-entry registry so handlers uniformly
    read from ``_registry.get(...)``.
    """
    global _runner, _registry
    if isinstance(runner_or_registry, AgentRunnerRegistry):
        _registry = runner_or_registry
        _runner = _registry.get(None)
    else:
        _runner = runner_or_registry
        # Wrap the single runner in a trivial registry so route handlers
        # can unconditionally talk to the registry. The builder simply
        # returns the same runner for any name — single-agent mode.
        single = runner_or_registry

        def _single_builder(_: str) -> AgentRunner:
            return single

        _registry = AgentRunnerRegistry(
            default_agent="orchestrator",
            builder=_single_builder,
        )
        _registry.register("orchestrator", single)
    return router


class ChatRequest(BaseModel):
    session_id: str
    message: str
    agent_name: str | None = None


class ChatResponse(BaseModel):
    text: str
    tool_calls: list[dict] = []
    is_final: bool = False


class EndSessionRequest(BaseModel):
    session_id: str
    agent_name: str | None = None


def _resolve_runner(agent_name: str | None) -> tuple[AgentRunner, str]:
    """Return ``(runner, effective_agent_name)`` for the requested agent.

    ``effective_agent_name`` is the non-empty name used for session
    scoping and logging. Falls back to the registry's default when the
    caller passed None/empty. Raises RuntimeError if neither a registry
    nor a legacy runner has been initialised — that would be a wiring
    bug in ``create_app``.
    """
    assert _registry is not None, (
        "chat router not initialised — init_chat_router must run "
        "before handling requests"
    )
    effective = agent_name or _registry.default_agent()
    return _registry.get(effective), effective


def _scoped_session_id(
    session_id: str, agent_name: str, default_agent: str
) -> str:
    """Namespace the session id for non-default agents.

    Default agent keeps the raw session_id (back-compat: existing
    clients that don't send ``agent_name`` hit the same session key
    they always did). Any other agent gets ``"{session_id}::{agent}"``
    so turn history stays isolated per agent.
    """
    if agent_name == default_agent:
        return session_id
    return f"{session_id}::{agent_name}"


@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    request: Request,
    user_id: str = Depends(get_current_user_id),
) -> ChatResponse:
    runner, effective_agent = _resolve_runner(req.agent_name)
    assert _registry is not None
    sid = _scoped_session_id(
        req.session_id, effective_agent, _registry.default_agent()
    )
    response = await runner.run(
        user_id=user_id,
        session_id=sid,
        message=req.message,
    )
    return ChatResponse(
        text=response.text,
        tool_calls=response.tool_calls,
        is_final=response.is_final,
    )


@router.post("/chat/end", status_code=204)
async def end_session(
    req: EndSessionRequest,
    user_id: str = Depends(get_current_user_id),
) -> None:
    runner, effective_agent = _resolve_runner(req.agent_name)
    assert _registry is not None
    sid = _scoped_session_id(
        req.session_id, effective_agent, _registry.default_agent()
    )
    await runner.end_session(user_id=user_id, session_id=sid)
