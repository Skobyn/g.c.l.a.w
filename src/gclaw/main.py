"""Cloud Run entry point — wires everything together and starts the server."""

from __future__ import annotations

import logging
import os

logging.basicConfig(level=logging.INFO)

from google.adk.sessions import InMemorySessionService

from gclaw.settings import get_settings
from gclaw.config.loader import ConfigLoader
from gclaw.agents.factory import AgentFactory
from gclaw.agents.orchestrator import build_orchestrator
from gclaw.board.service import BoardService
from gclaw.dispatch.runner import AgentRunner
from gclaw.firestore.client import get_firestore_client
from gclaw.firestore.board_repo import BoardRepo
from gclaw.firestore.session_repo import SessionRepo
from gclaw.session.service import SessionService
from gclaw.api.app import create_app

logger = logging.getLogger(__name__)


def _build_model_router(settings):
    """Build a ModelRouter from settings, or return None if disabled."""
    if not settings.model_routing_enabled:
        return None

    from gclaw.models.model_config import ModelEndpoint, TaskProfile, RoutingRule
    from gclaw.routing.router import ModelRouter

    endpoints: dict[str, ModelEndpoint] = {}
    rules: list[RoutingRule] = []

    # Gemini Flash — free tier default, always available
    endpoints["gemini-flash"] = ModelEndpoint(
        name="gemini-flash",
        endpoint_id=settings.gemini_flash_model,
        provider="gemini",
        max_context_tokens=1_000_000,
    )

    # Orchestrator uses Gemini Flash (free) — good enough for routing
    rules.append(RoutingRule(task_profile=TaskProfile.ORCHESTRATION, model_name="gemini-flash"))
    rules.append(RoutingRule(task_profile=TaskProfile.PERSONALITY, model_name="gemini-flash"))

    # Gemma 4 via Gemini API — free, same API surface
    if settings.gemma_endpoint_id:
        endpoints["gemma-4"] = ModelEndpoint(
            name="gemma-4",
            endpoint_id=settings.gemma_endpoint_id,
            provider="gemini",
            max_context_tokens=256_000,
        )
        rules.extend([
            RoutingRule(task_profile=TaskProfile.SUMMARIZATION, model_name="gemma-4"),
            RoutingRule(task_profile=TaskProfile.BACKGROUND, model_name="gemma-4"),
        ])
        logger.info("Gemma 4 registered (Gemini API): %s", settings.gemma_endpoint_id)

    # Nemotron via OpenRouter — free tier (wrapped with LiteLlm by the router)
    if settings.nemotron_endpoint_id and settings.openrouter_api_key:
        endpoints["nemotron-3-super"] = ModelEndpoint(
            name="nemotron-3-super",
            endpoint_id=settings.nemotron_endpoint_id,
            provider="openrouter",
            max_context_tokens=1_000_000,
        )
        rules.extend([
            RoutingRule(task_profile=TaskProfile.TOOL_EXECUTION, model_name="nemotron-3-super"),
            RoutingRule(task_profile=TaskProfile.CODE_GENERATION, model_name="nemotron-3-super"),
        ])
        logger.info("Nemotron 3 Super registered (OpenRouter via LiteLlm): %s", settings.nemotron_endpoint_id)

    return ModelRouter(
        endpoints=endpoints,
        rules=rules,
        default_model=settings.gemini_flash_model,
    )


def _init_firebase():
    """Initialize Firebase Admin SDK for auth token verification."""
    import firebase_admin
    if not firebase_admin._apps:
        firebase_admin.initialize_app()
        logger.info("Firebase Admin SDK initialized")


def _build_memory_service(settings):
    """Build MemoryService from settings, or return None if disabled."""
    if not settings.memory_enabled:
        return None

    import google.auth
    from gclaw.memory.client import MemoryBankClient
    from gclaw.memory.service import MemoryService

    credentials, _ = google.auth.default()

    # The reasoning engine ID can be a full resource path or just the numeric ID.
    # Extract the numeric ID if a full path is given.
    engine_id = settings.memory_bank_reasoning_engine_id
    if "/" in engine_id:
        # Full path: projects/.../reasoningEngines/123 → extract "123"
        engine_id = engine_id.rsplit("/", 1)[-1]

    client = MemoryBankClient(
        project_id=settings.gcp_project_id,
        location=settings.gcp_location,
        credentials=credentials,
        memory_bank_id=engine_id or "default",
    )
    logger.info("Memory Bank enabled (engine: %s)", engine_id)
    return MemoryService(client=client)


def build_app():
    settings = get_settings()

    # Firebase Auth
    if settings.firebase_auth_enabled:
        _init_firebase()

    # Firestore
    db = get_firestore_client(
        project=settings.gcp_project_id,
        database=settings.firestore_database,
    )

    # Board — user_id flows per-request from auth middleware
    # In dev mode (auth disabled), DevUserMiddleware sets a default user_id
    dev_user_id = os.environ.get("GCLAW_USER_ID", "default_user") if not settings.firebase_auth_enabled else None
    board_repo = BoardRepo(db=db, user_id=dev_user_id)
    board_service = BoardService(repo=board_repo, user_id=dev_user_id)

    # Model routing
    model_router = _build_model_router(settings)

    # Memory
    memory_service = _build_memory_service(settings)

    # Config + skills
    from gclaw.skill.loader import SkillLoader
    from gclaw.skill.registry import SkillRegistry
    from gclaw.skill.in_memory_repo import InMemorySkillRepo

    skill_loader = SkillLoader()
    loader = ConfigLoader(settings.config_dir, skill_loader=skill_loader)
    skill_registry = SkillRegistry(skill_repo=InMemorySkillRepo())
    loaded_skills = skill_registry.load_builtins(settings.skills_dir)
    logger.info("Loaded %d built-in skills", len(loaded_skills))

    factory = AgentFactory(
        loader=loader,
        default_model=settings.gemini_flash_model,
        model_router=model_router,
        skill_registry=skill_registry,
    )

    # Orchestrator
    orchestrator = build_orchestrator(
        factory=factory,
        board_service=board_service,
        router=model_router,
        default_model=settings.gemini_flash_model,
    )

    # ADK session service (in-flight execution state)
    session_service = InMemorySessionService()

    # Persistent session store — mirrors turns to Firestore so session
    # history survives restarts and end-of-session memory extraction has
    # a durable transcript to work from. Only wired in dev mode (fixed
    # user_id) for now; multi-tenant auth mode needs per-method user_id
    # threading through SessionRepo first.
    session_store: SessionService | None = None
    if dev_user_id is not None:
        session_repo = SessionRepo(db=db, user_id=dev_user_id)
        session_store = SessionService(
            session_repo=session_repo,
            memory_service=memory_service,
        )

    # Runner
    runner = AgentRunner(
        agent=orchestrator,
        app_name="gclaw",
        session_service=session_service,
        memory_service=memory_service,
        board_service=board_service,
        session_store=session_store,
    )

    return create_app(
        board_service=board_service,
        agent_runner=runner,
        model_router=model_router,
        memory_service=memory_service,
        enable_auth=settings.firebase_auth_enabled,
    )


app = build_app()

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
