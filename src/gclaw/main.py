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
from gclaw.firestore.usage_repo import UsageRepo
from gclaw.session.service import SessionService
from gclaw.usage.recorder import UsageRecorder, set_recorder
from gclaw.api.app import create_app

logger = logging.getLogger(__name__)


# Known-good Gemma model name patterns served by the Gemini API.
# Drifts as Google releases new models — if your target isn't here,
# add it or extend _looks_like_gemini_api_gemma.
_GEMINI_API_GEMMA_PATTERNS = (
    "gemma-3-",  # gemma-3-27b-it, gemma-3-12b-it, gemma-3-4b-it, gemma-3-1b-it
    "gemma-2-",  # gemma-2-27b-it, gemma-2-9b-it, gemma-2-2b-it (if still served)
)


def _looks_like_gemini_api_gemma(endpoint_id: str) -> bool:
    """True when `endpoint_id` matches a known Gemini-API Gemma pattern.

    Rejects Vertex AI Model Garden identifiers like "gemma-4-26b-it"
    or fully-qualified "publishers/google/models/..." paths that the
    Gemini API can't resolve directly.
    """
    if not endpoint_id:
        return False
    # Strip the "models/" prefix if present — Gemini API accepts either form.
    normalized = endpoint_id.removeprefix("models/")
    if "/" in normalized:
        # Anything with a slash (e.g. publishers/.../models/...) is a
        # Model Garden path and won't resolve on the Gemini API.
        return False
    return any(normalized.startswith(prefix) for prefix in _GEMINI_API_GEMMA_PATTERNS)


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

    # Gemma via Gemini API — free, same API surface.
    # The endpoint_id must be a Gemini-API-served model name (e.g.
    # "gemma-3-27b-it"), not a Vertex AI Model Garden identifier.
    # When misconfigured, managers using SUMMARIZATION/BACKGROUND
    # profiles fail downstream with "Model <id> not found" on every
    # LLM call. This check catches the common misconfigurations at
    # startup and *skips* registration rather than silently wiring
    # a broken endpoint.
    if settings.gemma_endpoint_id:
        if _looks_like_gemini_api_gemma(settings.gemma_endpoint_id):
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
            logger.info("Gemma registered (Gemini API): %s", settings.gemma_endpoint_id)
        else:
            logger.warning(
                "GEMMA_ENDPOINT_ID=%r does not look like a Gemini API model name "
                "(expected e.g. 'gemma-3-27b-it'). Skipping Gemma registration — "
                "SUMMARIZATION and BACKGROUND profiles will fall back to the "
                "default Gemini Flash model. See .env.example for valid formats.",
                settings.gemma_endpoint_id,
            )

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
    """Build a memory service from settings, or None if disabled.

    Backend selection:
      - `MEMORY_BACKEND=custom` (default) — hand-rolled MemoryBankClient
        + MemoryService. Preserves structured memory shape and the full
        feature set (shared channels, agent-scoped recall with merge).
      - `MEMORY_BACKEND=native` — ADK's VertexAiMemoryBankService wrapped
        by NativeMemoryService. Lean delegation to the blessed ADK path.
        Same public interface; loses some structured fields.
    """
    if not settings.memory_enabled:
        return None

    # The reasoning engine ID can be a full resource path or just the
    # numeric ID. Extract the numeric ID if a full path is given.
    engine_id = settings.memory_bank_reasoning_engine_id
    if "/" in engine_id:
        engine_id = engine_id.rsplit("/", 1)[-1]
    engine_id = engine_id or "default"

    backend = settings.memory_backend.strip().lower()
    if backend == "native":
        from google.adk.memory.vertex_ai_memory_bank_service import (
            VertexAiMemoryBankService,
        )
        from gclaw.memory.native_service import NativeMemoryService

        native = VertexAiMemoryBankService(
            project=settings.gcp_project_id,
            location=settings.gcp_location,
            agent_engine_id=engine_id,
        )
        logger.info(
            "Memory Bank enabled (backend=native, engine=%s)", engine_id
        )
        return NativeMemoryService(native=native, app_name="gclaw")

    if backend != "custom":
        logger.warning(
            "Unknown MEMORY_BACKEND=%r, falling back to 'custom'", backend
        )

    import google.auth
    from gclaw.memory.client import MemoryBankClient
    from gclaw.memory.service import MemoryService

    credentials, _ = google.auth.default()

    client = MemoryBankClient(
        project_id=settings.gcp_project_id,
        location=settings.gcp_location,
        credentials=credentials,
        memory_bank_id=engine_id,
    )
    logger.info("Memory Bank enabled (backend=custom, engine=%s)", engine_id)
    return MemoryService(client=client)


def _make_heartbeat_log_factory(db):
    """Return a callable uid → HeartbeatLogRepo for the admin dashboard."""
    from gclaw.heartbeat.log import HeartbeatLogRepo
    return lambda uid: HeartbeatLogRepo(db=db, user_id=uid)


def _iter_agent_names(config_dir: str) -> list[str]:
    """Return agent names discovered under ``config_dir/agents/*.md``."""
    agents_dir = os.path.join(config_dir, "agents")
    if not os.path.isdir(agents_dir):
        return []
    names: list[str] = []
    for fname in sorted(os.listdir(agents_dir)):
        if fname.endswith(".md"):
            names.append(fname.removesuffix(".md"))
    return names


def _build_heartbeat_registry(
    *,
    db,
    settings,
    dev_user_id,
    board_service,
    memory_service,
    session_store,
    runner,
    config_loader,
    delivery_service,
):
    """Build a HeartbeatRegistry containing one HeartbeatService per
    agent that opted into the heartbeat via YAML frontmatter.

    Always returns a registry (possibly empty). Returns ``None`` only
    when ``dev_user_id`` is absent (multi-tenant auth mode — per-user
    heartbeat scheduling is a follow-up).
    """
    if dev_user_id is None:
        return None

    from gclaw.cron.service import CronService
    from gclaw.firestore.cron_event_queue_repo import CronEventQueueRepo
    from gclaw.firestore.cron_repo import CronRepo
    from gclaw.heartbeat.context import HeartbeatContextGatherer
    from gclaw.heartbeat.log import HeartbeatLogRepo
    from gclaw.heartbeat.registry import HeartbeatRegistry
    from gclaw.heartbeat.service import HeartbeatService
    from gclaw.memory.consolidation import MemoryConsolidator

    cron_repo = CronRepo(db=db, user_id=dev_user_id)
    cron_event_queue_repo = CronEventQueueRepo(db=db, user_id=dev_user_id)
    cron_service = CronService(
        cron_repo=cron_repo,
        board_service=board_service,
        cron_event_queue_repo=cron_event_queue_repo,
        delivery_service=delivery_service,
    )
    context_gatherer = HeartbeatContextGatherer(
        board_service=board_service,
        cron_service=cron_service,
        memory_service=memory_service,
        user_id=dev_user_id,
    )
    log_repo = HeartbeatLogRepo(db=db, user_id=dev_user_id)
    consolidator = (
        MemoryConsolidator(memory_service=memory_service)
        if memory_service is not None
        else None
    )

    registry = HeartbeatRegistry()

    agent_names = _iter_agent_names(settings.config_dir)
    # Always ensure orchestrator is represented (even without frontmatter)
    # so legacy POST /heartbeat keeps working.
    if "orchestrator" not in agent_names:
        agent_names.insert(0, "orchestrator")

    for name in agent_names:
        try:
            cfg = config_loader.load_agent_heartbeat_config(name)
        except Exception:
            logger.warning(
                "Failed to load heartbeat config for agent %s", name,
                exc_info=True,
            )
            cfg = None

        # Orchestrator always gets a service (legacy trigger). Other
        # agents only get one if they opted in via frontmatter.
        if cfg is None:
            if name != "orchestrator":
                continue
            from gclaw.heartbeat.config import HeartbeatConfig
            cfg = HeartbeatConfig(enabled=False)

        service = HeartbeatService(
            context_gatherer=context_gatherer,
            agent_runner=runner,
            log_repo=log_repo,
            user_id=dev_user_id,
            session_id=settings.heartbeat_session_id,
            consolidator=consolidator,
            session_store=session_store,
            stale_session_threshold_seconds=(
                settings.stale_session_threshold_seconds
            ),
            agent_name=name,
            heartbeat_config=cfg,
            cron_event_queue_repo=cron_event_queue_repo,
        )
        registry.register(name, service, cfg)

    logger.info(
        "heartbeat: registered %d agent service(s): %s",
        len(registry.all_agents()),
        registry.all_agents(),
    )
    return registry


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

    # Catalog (providers + models)
    catalog_service = None
    if settings.catalog_enabled:
        from gclaw.catalog.service import CatalogService
        from gclaw.firestore.catalog_repo import ModelRepo, ProviderRepo
        catalog_service = CatalogService(
            provider_repo=ProviderRepo(db=db),
            model_repo=ModelRepo(db=db),
        )
        try:
            catalog_service.seed_system_defaults(settings=settings)
        except Exception:
            logger.warning("catalog: seed_system_defaults failed", exc_info=True)

    # Model routing — prefer catalog-backed router when populated.
    model_router = None
    if (
        settings.catalog_enabled
        and settings.model_routing_enabled
        and catalog_service is not None
    ):
        try:
            enabled_models = [
                m for m in catalog_service.list_models() if m.enabled
            ]
        except Exception:
            enabled_models = []
            logger.warning(
                "catalog: list_models failed, falling back to hardcoded router",
                exc_info=True,
            )
        if enabled_models:
            from gclaw.routing.catalog_loader import load_endpoints_from_catalog
            model_router = load_endpoints_from_catalog(
                catalog_service,
                fallback_flash_model=settings.gemini_flash_model,
            )
            logger.info(
                "model router: loaded %d endpoints from catalog",
                len(enabled_models),
            )
    if model_router is None:
        model_router = _build_model_router(settings)

    # Memory
    memory_service = _build_memory_service(settings)

    # Cron service — used by admin routes + heartbeat. The delivery
    # service is constructed ONCE and shared with both the user-facing
    # CronService (admin API) and the per-agent CronService inside the
    # heartbeat registry, so there's a single announce transport in
    # flight at any time.
    from gclaw.cron.delivery import (
        CronDeliveryService,
        build_transport_registry,
    )
    from gclaw.cron.service import CronService
    from gclaw.firestore.cron_repo import CronRepo
    cron_repo = CronRepo(db=db, user_id=dev_user_id or "default_user")
    transports, default_transport = build_transport_registry(settings)
    cron_delivery = CronDeliveryService(
        transports=transports,
        default_transport=default_transport,
    )
    cron_service = CronService(
        cron_repo=cron_repo,
        board_service=board_service,
        delivery_service=cron_delivery,
    )

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
        catalog_service=catalog_service,
    )

    # Orchestrator
    orchestrator = build_orchestrator(
        factory=factory,
        board_service=board_service,
        router=model_router,
        default_model=settings.gemini_flash_model,
        memory_service=memory_service,
    )

    # ADK session service (in-flight execution state)
    session_service = InMemorySessionService()

    # Persistent session store — mirrors turns to Firestore so session
    # history survives restarts and end-of-session memory extraction has
    # a durable transcript to work from. Constructed unconditionally; in
    # auth mode the per-request user_id flows in via
    # AgentRunner.set_active_user(user_id) → SessionService.set_active_user.
    session_repo = SessionRepo(db=db, user_id=dev_user_id)
    session_store = SessionService(
        session_repo=session_repo,
        memory_service=memory_service,
        user_id=dev_user_id,
    )

    # Usage telemetry — records model/agent/skill/tool events.
    usage_repo = UsageRepo(db=db, user_id=dev_user_id or "system")
    cost_lookup = None
    if catalog_service is not None:
        from gclaw.usage.cost import build_catalog_cost_lookup
        cost_lookup = build_catalog_cost_lookup(catalog_service)
    usage_recorder = UsageRecorder(
        repo=usage_repo,
        enabled=settings.usage_telemetry_enabled,
        cost_lookup=cost_lookup,
    )
    set_recorder(usage_recorder)

    # Runner
    runner = AgentRunner(
        agent=orchestrator,
        app_name="gclaw",
        session_service=session_service,
        memory_service=memory_service,
        board_service=board_service,
        session_store=session_store,
        usage_recorder=usage_recorder,
    )

    # Heartbeat — consciousness loop triggered by Cloud Scheduler POST /heartbeat
    # and (when HEARTBEAT_PER_AGENT_ENABLED) by the in-process background
    # loop. Dev mode only for now; multi-tenant heartbeat scheduling is a
    # follow-up.
    heartbeat_registry = _build_heartbeat_registry(
        db=db,
        settings=settings,
        dev_user_id=dev_user_id,
        board_service=board_service,
        memory_service=memory_service,
        session_store=session_store,
        runner=runner,
        config_loader=loader,
        delivery_service=cron_delivery,
    )
    # Default/legacy service — the orchestrator's, for POST /heartbeat.
    heartbeat_service = (
        heartbeat_registry.get("orchestrator")
        if heartbeat_registry is not None
        else None
    )

    return create_app(
        board_service=board_service,
        agent_runner=runner,
        model_router=model_router,
        memory_service=memory_service,
        config_loader=loader,
        skill_registry=skill_registry,
        cron_service=cron_service,
        cron_delivery_service=cron_delivery,
        heartbeat_service=heartbeat_service,
        heartbeat_registry=heartbeat_registry,
        heartbeat_loop_enabled=settings.heartbeat_per_agent_enabled,
        heartbeat_scheduler_seed=settings.heartbeat_scheduler_seed,
        heartbeat_log_repo_factory=(
            _make_heartbeat_log_factory(db)
        ) if dev_user_id is not None else None,
        enable_auth=settings.firebase_auth_enabled,
        catalog_service=catalog_service,
        usage_repo=usage_repo,
    )


# Lazy factory so importing this module for tests (e.g. importing
# _looks_like_gemini_api_gemma) doesn't trigger build_app() which
# requires GCP_PROJECT_ID and other env vars not present in CI.
# uvicorn calls the factory via --factory flag; the Dockerfile's
# CMD already uses `python -m gclaw.main` which hits __main__.
def app():
    return build_app()


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("gclaw.main:app", factory=True, host="0.0.0.0", port=port)
