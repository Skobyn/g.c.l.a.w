"""Cloud Run entry point — wires everything together and starts the server."""

from __future__ import annotations

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

    # Config
    loader = ConfigLoader(settings.config_dir)
    factory = AgentFactory(
        loader=loader,
        default_model=settings.gemini_pro_model,
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
