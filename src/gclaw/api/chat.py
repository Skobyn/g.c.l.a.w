"""Chat endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from gclaw.auth.dependencies import get_current_user_id
from gclaw.dispatch.runner import AgentRunner

router = APIRouter()

_runner: AgentRunner | None = None


def init_chat_router(runner: AgentRunner) -> APIRouter:
    global _runner
    _runner = runner
    return router


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    text: str
    tool_calls: list[dict] = []
    is_final: bool = False


class EndSessionRequest(BaseModel):
    session_id: str


@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    request: Request,
    user_id: str = Depends(get_current_user_id),
) -> ChatResponse:
    response = await _runner.run(
        user_id=user_id,
        session_id=req.session_id,
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
    await _runner.end_session(user_id=user_id, session_id=req.session_id)
