"""FastAPI app factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

from gclaw.api.admin_routes import init_admin_router
from gclaw.api.agent_config_routes import init_agent_config_router
from gclaw.api.catalog_routes import init_catalog_router
from gclaw.api.context_routes import init_context_router
from gclaw.api.usage_routes import init_usage_router
from gclaw.api.chat import init_chat_router
from gclaw.api.board_routes import init_board_router
from gclaw.api.connection_routes import init_connection_router
from gclaw.api.cron_routes import init_cron_router
from gclaw.api.heartbeat_routes import init_heartbeat_router
from gclaw.api.onboarding_routes import init_onboarding_router
from gclaw.api.routing_routes import init_routing_router
from gclaw.api.secrets_routes import init_secrets_router
from gclaw.api.tool_routes import init_tool_router
from gclaw.api.voice_ws import init_voice_router
from gclaw.auth.middleware import FirebaseAuthMiddleware
from gclaw.board.service import BoardService
from gclaw.connection.service import ConnectionService
from gclaw.cron.service import CronService
from gclaw.dispatch.runner import AgentRunner
from gclaw.dispatch.runner_registry import AgentRunnerRegistry
from gclaw.onboarding.service import OnboardingService


def create_app(
    board_service: BoardService,
    agent_runner: AgentRunner,
    agent_runner_registry: AgentRunnerRegistry | None = None,
    cron_service: CronService | None = None,
    cron_delivery_service: object | None = None,
    heartbeat_service: object | None = None,
    session_service: object | None = None,
    session_store: object | None = None,
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
    agent_config_service: object | None = None,
    shared_context_service: object | None = None,
    secret_manager_service: object | None = None,
    oauth_manager: object | None = None,
    oauth_loop_enabled: bool = False,
    oauth_refresh_interval_seconds: int = 300,
    system_config_repo: object | None = None,
    run_registry: object | None = None,
    user_event_registry: object | None = None,
    agent_runs_repo: object | None = None,
    tool_catalog_service: object | None = None,
    vertex_scorer: object | None = None,
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

        if oauth_loop_enabled and oauth_manager is not None:
            from gclaw.catalog.oauth_refresh_loop import OAuthRefreshLoop

            oauth_loop = OAuthRefreshLoop(
                oauth_manager,  # type: ignore[arg-type]
                check_interval_seconds=oauth_refresh_interval_seconds,
            )
            oauth_loop.start()
            _loop_holder["oauth_loop"] = oauth_loop
            logger.info("oauth-refresh: background loop started")
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
            oauth_loop = _loop_holder.get("oauth_loop")
            if oauth_loop is not None:
                try:
                    await oauth_loop.stop()
                    logger.info("oauth-refresh: background loop stopped")
                except Exception:
                    logger.warning(
                        "oauth-refresh: background loop stop failed",
                        exc_info=True,
                    )

    app = FastAPI(title="GClaw", version="0.4.0", lifespan=lifespan)

    # Middleware ordering: Starlette applies add_middleware in reverse,
    # so the LAST one added is the OUTERMOST. CORS must be outermost
    # so its headers are attached to error responses (500s) too,
    # otherwise browsers report "No Access-Control-Allow-Origin" on
    # backend exceptions and the real error stays invisible in the
    # browser console.
    #
    # Also: allow_origins=["*"] + allow_credentials=True is invalid per
    # the CORS spec — Starlette silently drops the ACAO header in that
    # combo. Use allow_origin_regex=".*" (echoes caller's Origin,
    # credential-compatible) as the permissive default, with
    # CORS_ORIGINS env as an exact-match tightening for prod.
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

    import os as _os
    cors_env = _os.environ.get("CORS_ORIGINS", "").strip()
    if cors_env:
        allowed = [o.strip() for o in cors_env.split(",") if o.strip()]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    else:
        app.add_middleware(
            CORSMiddleware,
            allow_origin_regex=".*",
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Prefer the multi-agent registry when wired; fall back to the single
    # runner for legacy callers (tests, eval harness).
    app.include_router(
        init_chat_router(
            agent_runner_registry or agent_runner,
            session_store=session_store,
        )
    )
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

    # Mount the agent-config router BEFORE the admin router so its
    # richer /admin/agents shadows the legacy fallback.
    if agent_config_service is not None:
        app.include_router(init_agent_config_router(
            agent_config_service=agent_config_service,
            config_loader=config_loader,
        ))
        app.state.agent_config_service = agent_config_service

    if tool_catalog_service is not None:
        app.include_router(init_tool_router(tool_catalog_service))

    if vertex_scorer is not None:
        from gclaw.api.scoring_routes import init_scoring_router
        app.include_router(init_scoring_router(scorer=vertex_scorer))

    if config_loader is not None and skill_registry is not None:
        app.include_router(init_admin_router(
            config_loader=config_loader,
            heartbeat_log_repo_factory=heartbeat_log_repo_factory,
            skill_registry=skill_registry,
            memory_service=memory_service,
            cron_service=cron_service,
            heartbeat_registry=heartbeat_registry,
            cron_delivery_service=cron_delivery_service,
            system_config_repo=system_config_repo,
        ))

    if connection_service is not None:
        app.include_router(init_connection_router(connection_service))

    if onboarding_service is not None:
        app.include_router(init_onboarding_router(onboarding_service))

    app.include_router(init_routing_router(model_router))

    app.include_router(init_usage_router(usage_repo))  # type: ignore[arg-type]

    # Live observability dashboard — SSE feed for /admin/live widgets.
    # Mounted only when the LiveSpanProcessor/RunRegistry were wired up
    # (i.e. OBSERVABILITY_ENABLED=true in main.py).
    if run_registry is not None:
        from gclaw.api.dashboard_routes import build_dashboard_router
        owner_lookup = None
        if agent_runs_repo is not None:
            owner_lookup = (
                lambda uid, rid: agent_runs_repo.get_owner(  # type: ignore[attr-defined]
                    rid, uid
                )
            )
        app.include_router(
            build_dashboard_router(
                run_registry=run_registry,  # type: ignore[arg-type]
                owner_lookup=owner_lookup,
            )
        )
        app.state.run_registry = run_registry
        app.state.agent_runs_repo = agent_runs_repo

    # User-scoped event feed — drains task.* events produced anywhere
    # in the system for the authenticated user. Always mounted when a
    # UserEventRegistry is wired (independent of observability flag).
    if user_event_registry is not None:
        from gclaw.api.events_routes import build_events_router
        app.include_router(
            build_events_router(
                user_event_registry=user_event_registry,  # type: ignore[arg-type]
            )
        )
        app.state.user_event_registry = user_event_registry

    if catalog_service is not None:
        app.include_router(init_catalog_router(catalog_service))
        app.state.catalog_service = catalog_service

    if secret_manager_service is not None:
        app.include_router(init_secrets_router(
            secret_manager_service,  # type: ignore[arg-type]
            oauth_manager=oauth_manager,
        ))
        app.state.secret_manager_service = secret_manager_service
        app.state.oauth_manager = oauth_manager

    if shared_context_service is not None:
        app.include_router(init_context_router(shared_context_service))  # type: ignore[arg-type]
        app.state.shared_context_service = shared_context_service

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
