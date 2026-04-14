"""FastAPI app factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

from gclaw.api.admin_routes import init_admin_router
from gclaw.api.catalog_routes import init_catalog_router
from gclaw.api.usage_routes import init_usage_router
from gclaw.api.chat import init_chat_router
from gclaw.api.board_routes import init_board_router
from gclaw.api.connection_routes import init_connection_router
from gclaw.api.cron_routes import init_cron_router
from gclaw.api.heartbeat_routes import init_heartbeat_router
from gclaw.api.onboarding_routes import init_onboarding_router
from gclaw.api.routing_routes import init_routing_router
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
    cron_delivery_service: object | None = None,
    heartbeat_service: object | None = None,
    session_service: object | None = None,
    memory_service: object | None = None,
    skill_registry: object | None = None,
    config_loader: object | None = None,
    heartbeat_log_repo_factory: object | None = None,
    connection_service: ConnectionService | None = None,
    onboarding_service: OnboardingService | None = None,
    model_router: object | None = None,
    catalog_service: object | None = None,
    enable_auth: bool = False,
    gemini_live_model: str = "gemini-2.5-flash-preview-native-audio",
    heartbeat_registry: object | None = None,
    heartbeat_loop_enabled: bool = False,
    heartbeat_scheduler_seed: str = "gclaw-default-seed",
    usage_repo: object | None = None,
) -> FastAPI:
    # Lifespan that optionally starts the per-agent heartbeat loop.
    _loop_holder: dict = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if (
            heartbeat_loop_enabled
            and heartbeat_registry is not None
            and getattr(heartbeat_registry, "all_agents", lambda: [])()
        ):
            from gclaw.heartbeat.scheduler_loop import HeartbeatLoop

            loop = HeartbeatLoop(
                heartbeat_registry, seed=heartbeat_scheduler_seed
            )
            loop.start()
            _loop_holder["loop"] = loop
            logger.info("heartbeat: background loop started")
        try:
            yield
        finally:
            loop = _loop_holder.get("loop")
            if loop is not None:
                try:
                    await loop.stop()
                    logger.info("heartbeat: background loop stopped")
                except Exception:
                    logger.warning(
                        "heartbeat: background loop stop failed",
                        exc_info=True,
                    )

    app = FastAPI(title="GClaw", version="0.4.0", lifespan=lifespan)

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

    if heartbeat_service is not None or heartbeat_registry is not None:
        app.include_router(
            init_heartbeat_router(
                heartbeat_service, registry=heartbeat_registry
            )
        )

    app.include_router(init_voice_router(gemini_live_model))

    if config_loader is not None and skill_registry is not None:
        app.include_router(init_admin_router(
            config_loader=config_loader,
            heartbeat_log_repo_factory=heartbeat_log_repo_factory,
            skill_registry=skill_registry,
            memory_service=memory_service,
            cron_service=cron_service,
            heartbeat_registry=heartbeat_registry,
            cron_delivery_service=cron_delivery_service,
        ))

    if connection_service is not None:
        app.include_router(init_connection_router(connection_service))

    if onboarding_service is not None:
        app.include_router(init_onboarding_router(onboarding_service))

    app.include_router(init_routing_router(model_router))

    app.include_router(init_usage_router(usage_repo))  # type: ignore[arg-type]

    if catalog_service is not None:
        app.include_router(init_catalog_router(catalog_service))
        app.state.catalog_service = catalog_service

    # Store services on app state for use by future route extensions
    app.state.session_service = session_service
    app.state.memory_service = memory_service
    app.state.skill_registry = skill_registry
    app.state.connection_service = connection_service
    app.state.onboarding_service = onboarding_service
    app.state.heartbeat_registry = heartbeat_registry
    app.state.cron_delivery_service = cron_delivery_service

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/")
    def root():
        """Minimal landing JSON — hitting the bare URL in a browser
        used to return FastAPI's default 404. This handler gives
        visitors a pointer to the API explorer and the main endpoints.
        """
        return {
            "service": "GClaw",
            "version": app.version,
            "docs": "/docs",
            "health": "/health",
            "chat": {
                "send": "POST /chat",
                "end": "POST /chat/end",
            },
            "board": "GET /board/tasks",
            "heartbeat": "POST /heartbeat",
        }

    return app
