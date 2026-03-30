"""FastAPI app factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from gclaw.api.chat import init_chat_router
from gclaw.api.board_routes import init_board_router
from gclaw.board.service import BoardService
from gclaw.dispatch.runner import AgentRunner


def create_app(
    board_service: BoardService,
    agent_runner: AgentRunner,
) -> FastAPI:
    app = FastAPI(title="GClaw", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(init_chat_router(agent_runner))
    app.include_router(init_board_router(board_service))

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app
