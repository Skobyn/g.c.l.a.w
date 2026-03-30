"""Chat endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from gclaw.dispatch.runner import AgentRunner

router = APIRouter()

_runner: AgentRunner | None = None


def init_chat_router(runner: AgentRunner) -> APIRouter:
    global _runner
    _runner = runner
    return router


class ChatRequest(BaseModel):
    user_id: str
    session_id: str
    message: str


class ChatResponse(BaseModel):
    text: str
    tool_calls: list[dict] = []
    is_final: bool = False


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    response = await _runner.run(
        user_id=req.user_id,
        session_id=req.session_id,
        message=req.message,
    )
    return ChatResponse(
        text=response.text,
        tool_calls=response.tool_calls,
        is_final=response.is_final,
    )
