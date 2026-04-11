"""Admin endpoints for model routing status and resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter

from gclaw.models.model_config import TaskProfile

if TYPE_CHECKING:
    from gclaw.routing.router import ModelRouter


def init_routing_router(model_router: ModelRouter | None) -> APIRouter:
    router = APIRouter(prefix="/routing", tags=["routing"])

    @router.get("/status")
    def routing_status():
        if model_router is None:
            return {"enabled": False, "endpoints": [], "rules": []}

        return {
            "enabled": True,
            "endpoints": [
                {
                    "name": ep.name,
                    "endpoint_id": ep.endpoint_id,
                    "provider": ep.provider,
                    "max_context_tokens": ep.max_context_tokens,
                }
                for ep in model_router._endpoints.values()
            ],
            "rules": [
                {"profile": profile.value, "model": name}
                for profile, name in model_router._rules.items()
            ],
        }

    @router.get("/resolve/{profile}")
    def resolve_profile(profile: str):
        if model_router is None:
            return {"profile": profile, "model_id": None, "enabled": False}

        task_profile = TaskProfile(profile)
        model_id = model_router.resolve(task_profile)
        endpoint = model_router.get_endpoint(task_profile)
        return {
            "profile": profile,
            "model_id": model_id,
            "endpoint": {
                "name": endpoint.name,
                "provider": endpoint.provider,
                "max_context_tokens": endpoint.max_context_tokens,
            } if endpoint else None,
        }

    @router.get("/resolve-agent/{agent_name}")
    def resolve_agent(agent_name: str):
        if model_router is None:
            return {"agent_name": agent_name, "model_id": None, "enabled": False}

        model_id = model_router.resolve_for_agent(agent_name)
        return {
            "agent_name": agent_name,
            "model_id": model_id,
        }

    return router
