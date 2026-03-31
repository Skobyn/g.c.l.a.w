"""FastAPI app factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from gclaw.api.chat import init_chat_router
from gclaw.api.board_routes import init_board_router
from gclaw.api.cron_routes import init_cron_router
from gclaw.api.heartbeat_routes import init_heartbeat_router
from gclaw.auth.middleware import FirebaseAuthMiddleware
from gclaw.board.service import BoardService
from gclaw.cron.service import CronService
from gclaw.dispatch.runner import AgentRunner


def create_app(
    board_service: BoardService,
    agent_runner: AgentRunner,
    cron_service: CronService | None = None,
    heartbeat_service: object | None = None,
    session_service: object | None = None,
    memory_service: object | None = None,
    skill_registry: object | None = None,
    enable_auth: bool = False,
) -> FastAPI:
    app = FastAPI(title="GClaw", version="0.4.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if enable_auth:
        app.add_middleware(FirebaseAuthMiddleware)

    app.include_router(init_chat_router(agent_runner))
    app.include_router(init_board_router(board_service))

    if cron_service is not None:
        app.include_router(init_cron_router(cron_service))

    if heartbeat_service is not None:
        app.include_router(init_heartbeat_router(heartbeat_service))

    # Store services on app state for use by future route extensions
    app.state.session_service = session_service
    app.state.memory_service = memory_service
    app.state.skill_registry = skill_registry

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app
