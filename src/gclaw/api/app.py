"""FastAPI app factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from gclaw.api.admin_routes import init_admin_router
from gclaw.api.chat import init_chat_router
from gclaw.api.board_routes import init_board_router
from gclaw.api.connection_routes import init_connection_router
from gclaw.api.cron_routes import init_cron_router
from gclaw.api.heartbeat_routes import init_heartbeat_router
from gclaw.api.onboarding_routes import init_onboarding_router
from gclaw.api.voice_ws import init_voice_router
from gclaw.auth.middleware import FirebaseAuthMiddleware
from gclaw.board.service import BoardService
from gclaw.connection.service import ConnectionService
from gclaw.cron.service import CronService
from gclaw.dispatch.runner import AgentRunner
from gclaw.onboarding.service import OnboardingService


def create_app(
    board_service: BoardService,
    agent_runner: AgentRunner,
    cron_service: CronService | None = None,
    heartbeat_service: object | None = None,
    session_service: object | None = None,
    memory_service: object | None = None,
    skill_registry: object | None = None,
    config_loader: object | None = None,
    heartbeat_log_repo_factory: object | None = None,
    connection_service: ConnectionService | None = None,
    onboarding_service: OnboardingService | None = None,
    enable_auth: bool = False,
    gemini_live_model: str = "gemini-2.5-flash-preview-native-audio",
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
    else:
        # Dev mode: set a default user_id so auth dependencies work
        from starlette.middleware.base import BaseHTTPMiddleware

        class DevUserMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                import os
                request.state.user_id = os.environ.get("GCLAW_USER_ID", "default_user")
                return await call_next(request)

        app.add_middleware(DevUserMiddleware)

    app.include_router(init_chat_router(agent_runner))
    app.include_router(init_board_router(board_service))

    if cron_service is not None:
        app.include_router(init_cron_router(cron_service))

    if heartbeat_service is not None:
        app.include_router(init_heartbeat_router(heartbeat_service))

    app.include_router(init_voice_router(gemini_live_model))

    if (
        config_loader is not None
        and skill_registry is not None
        and memory_service is not None
    ):
        app.include_router(init_admin_router(
            config_loader=config_loader,
            heartbeat_log_repo_factory=heartbeat_log_repo_factory,
            skill_registry=skill_registry,
            memory_service=memory_service,
            cron_service=cron_service,
        ))

    if connection_service is not None:
        app.include_router(init_connection_router(connection_service))

    if onboarding_service is not None:
        app.include_router(init_onboarding_router(onboarding_service))

    # Store services on app state for use by future route extensions
    app.state.session_service = session_service
    app.state.memory_service = memory_service
    app.state.skill_registry = skill_registry
    app.state.connection_service = connection_service
    app.state.onboarding_service = onboarding_service

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app
