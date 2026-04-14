"""Admin API for agent configuration (Firestore-backed overrides)."""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel

from gclaw.auth.dependencies import get_current_user_id
from gclaw.config.agent_config_service import AgentConfigService

logger = logging.getLogger(__name__)

PROTECTED_AGENTS: frozenset[str] = frozenset({
    "orchestrator",
    "workspace-mgr",
    "dev-mgr",
    "home-mgr",
    "comms-mgr",
    "research-mgr",
})


class CreateAgentRequest(BaseModel):
    agent_name: str
    body: str
    display_name: str | None = None
    description: str | None = None
    emoji: str | None = None
    model_primary: str | None = None
    soul_overlay: str | None = None


def init_agent_config_router(
    agent_config_service: AgentConfigService | None,
    config_loader: Any = None,
) -> APIRouter:
    """Build the /admin/agents router.

    When ``agent_config_service`` is None, falls back to the legacy
    scan-based listing so nothing breaks.
    """
    router = APIRouter(prefix="/admin")

    @router.get("/agents")
    def list_agents(user_id: str = Depends(get_current_user_id)):
        if agent_config_service is None:
            # Legacy fallback — mirrors the old admin_routes behaviour.
            if config_loader is None:
                return []
            agents_dir = os.path.join(config_loader._config_dir, "agents")
            out: list[dict] = []
            if os.path.isdir(agents_dir):
                for fname in sorted(os.listdir(agents_dir)):
                    if fname.endswith(".md"):
                        name = fname.removesuffix(".md")
                        soul_dir = os.path.join(
                            config_loader._config_dir, "soul"
                        )
                        has_overlay = os.path.isfile(os.path.join(
                            soul_dir, f"{name.split('-')[0]}.md"
                        ))
                        out.append({
                            "name": name, "has_soul_overlay": has_overlay,
                        })
            return out
        return agent_config_service.list_agents()

    @router.get("/agents/{name}")
    def get_agent(name: str, user_id: str = Depends(get_current_user_id)):
        if agent_config_service is None:
            raise HTTPException(
                status_code=503,
                detail="Agent config service not configured",
            )
        try:
            return agent_config_service.get_effective_config(name)
        except FileNotFoundError:
            raise HTTPException(
                status_code=404, detail=f"Agent {name!r} not found"
            )

    @router.get("/agents/{name}/override")
    def get_agent_override(
        name: str, user_id: str = Depends(get_current_user_id)
    ):
        if agent_config_service is None:
            raise HTTPException(
                status_code=503,
                detail="Agent config service not configured",
            )
        override = agent_config_service.get_override(name)
        if override is None:
            raise HTTPException(
                status_code=404, detail=f"No override for {name!r}"
            )
        return override.model_dump(mode="json")

    @router.post("/agents")
    def create_agent(
        req: CreateAgentRequest,
        user_id: str = Depends(get_current_user_id),
    ):
        if agent_config_service is None:
            raise HTTPException(
                status_code=503,
                detail="Agent config service not configured",
            )
        try:
            override = agent_config_service.create_standalone(
                agent_name=req.agent_name,
                body=req.body,
                display_name=req.display_name,
                description=req.description,
                emoji=req.emoji,
                model_primary=req.model_primary,
                soul_overlay=req.soul_overlay,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return override.model_dump(mode="json")

    @router.patch("/agents/{name}")
    def patch_agent(
        name: str,
        patch: dict = Body(default_factory=dict),
        user_id: str = Depends(get_current_user_id),
    ):
        if agent_config_service is None:
            raise HTTPException(
                status_code=503,
                detail="Agent config service not configured",
            )
        try:
            override = agent_config_service.upsert_override(name, patch)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return override.model_dump(mode="json")

    @router.delete("/agents/{name}")
    def delete_agent(
        name: str,
        force: bool = Query(False),
        user_id: str = Depends(get_current_user_id),
    ):
        if agent_config_service is None:
            raise HTTPException(
                status_code=503,
                detail="Agent config service not configured",
            )
        if name in PROTECTED_AGENTS and not force:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Agent {name!r} is protected — pass ?force=true to "
                    "delete its override"
                ),
            )
        result = agent_config_service.delete_override(name)
        return result

    @router.get("/agents/{name}/baseline")
    def get_agent_baseline(
        name: str, user_id: str = Depends(get_current_user_id)
    ):
        if agent_config_service is None:
            raise HTTPException(
                status_code=503,
                detail="Agent config service not configured",
            )
        content = agent_config_service.read_baseline(name)
        if content is None:
            raise HTTPException(
                status_code=404,
                detail=f"No baseline .md for {name!r}",
            )
        return {"name": name, "content": content}

    return router
