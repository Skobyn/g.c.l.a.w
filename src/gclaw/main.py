"""Cloud Run entry point — wires everything together and starts the server."""

from __future__ import annotations

import logging
import os

from google.adk.sessions import InMemorySessionService

from gclaw.settings import get_settings
from gclaw.config.loader import ConfigLoader
from gclaw.agents.factory import AgentFactory
from gclaw.agents.orchestrator import build_orchestrator
from gclaw.board.service import BoardService
from gclaw.dispatch.runner import AgentRunner
from gclaw.firestore.client import get_firestore_client
from gclaw.firestore.board_repo import BoardRepo
from gclaw.api.app import create_app

logger = logging.getLogger(__name__)


def _build_model_router(settings):
    """Build a ModelRouter from settings, or return None if disabled."""
    if not settings.model_routing_enabled:
        return None

    from gclaw.models.model_config import ModelEndpoint, TaskProfile, RoutingRule
    from gclaw.routing.router import ModelRouter

    endpoints: dict[str, ModelEndpoint] = {
        "gemini-pro": ModelEndpoint(
            name="gemini-pro",
            endpoint_id=settings.gemini_pro_model,
            max_context_tokens=1_000_000,
        ),
    }

    rules: list[RoutingRule] = [
        RoutingRule(task_profile=TaskProfile.ORCHESTRATION, model_name="gemini-pro"),
        RoutingRule(task_profile=TaskProfile.PERSONALITY, model_name="gemini-pro"),
    ]

    # Register Gemma 4 endpoint if configured
    if settings.gemma_endpoint_id:
        endpoints["gemma-4"] = ModelEndpoint(
            name="gemma-4",
            endpoint_id=settings.gemma_endpoint_id,
            max_context_tokens=256_000,
        )
        rules.extend([
            RoutingRule(task_profile=TaskProfile.SUMMARIZATION, model_name="gemma-4"),
            RoutingRule(task_profile=TaskProfile.BACKGROUND, model_name="gemma-4"),
        ])
        logger.info("Gemma 4 endpoint registered: %s", settings.gemma_endpoint_id)

    # Register Nemotron endpoint if configured
    if settings.nemotron_endpoint_id:
        endpoints["nemotron-3-super"] = ModelEndpoint(
            name="nemotron-3-super",
            endpoint_id=settings.nemotron_endpoint_id,
            max_context_tokens=1_000_000,
            provider=settings.nemotron_provider,
        )
        rules.extend([
            RoutingRule(task_profile=TaskProfile.TOOL_EXECUTION, model_name="nemotron-3-super"),
            RoutingRule(task_profile=TaskProfile.CODE_GENERATION, model_name="nemotron-3-super"),
        ])
        logger.info("Nemotron 3 Super endpoint registered: %s", settings.nemotron_endpoint_id)

    return ModelRouter(
        endpoints=endpoints,
        rules=rules,
        default_model=settings.gemini_pro_model,
    )


def build_app():
    settings = get_settings()

    # Firestore
    db = get_firestore_client(
        project=settings.gcp_project_id,
        database=settings.firestore_database,
    )

    # For now, use a hardcoded user ID — Plan 4 adds Firebase Auth
    user_id = os.environ.get("GCLAW_USER_ID", "default_user")

    # Board
    board_repo = BoardRepo(db=db, user_id=user_id)
    board_service = BoardService(repo=board_repo)

    # Model routing
    model_router = _build_model_router(settings)

    # Config
    loader = ConfigLoader(settings.config_dir)
    factory = AgentFactory(
        loader=loader,
        default_model=settings.gemini_pro_model,
        model_router=model_router,
    )

    # Orchestrator
    orchestrator = build_orchestrator(
        factory=factory,
        board_service=board_service,
    )

    # Session service (in-memory for now — Plan 3 adds Firestore sessions)
    session_service = InMemorySessionService()

    # Runner
    runner = AgentRunner(
        agent=orchestrator,
        app_name="gclaw",
        session_service=session_service,
    )

    return create_app(board_service=board_service, agent_runner=runner)


app = build_app()

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
