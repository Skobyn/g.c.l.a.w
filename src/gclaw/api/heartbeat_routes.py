"""Heartbeat trigger endpoint.

Cloud Scheduler hits POST /heartbeat to wake the orchestrator's
consciousness loop. This is not a health check — it triggers the
orchestrator (or any registered agent) to scan the world state and
decide what to do.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from gclaw.heartbeat.reason import WakeReason
from gclaw.heartbeat.service import HeartbeatService

router = APIRouter()

_heartbeat_service: HeartbeatService | None = None
_registry: object | None = None


def init_heartbeat_router(
    heartbeat_service: HeartbeatService | None,
    registry: object | None = None,
) -> APIRouter:
    global _heartbeat_service, _registry
    _heartbeat_service = heartbeat_service
    _registry = registry
    return router


def _resolve_service(agent_id: str | None) -> HeartbeatService | None:
    if agent_id and _registry is not None:
        svc = _registry.get(agent_id)  # type: ignore[attr-defined]
        if svc is not None:
            return svc
    if _registry is not None and _heartbeat_service is None:
        svc = _registry.get("orchestrator")  # type: ignore[attr-defined]
        if svc is not None:
            return svc
    return _heartbeat_service


@router.post("/heartbeat")
async def trigger_heartbeat(agent_id: str | None = None):
    """Trigger a heartbeat cycle.

    Called by Cloud Scheduler at a configurable interval (default: 15 min).
    When ``agent_id`` is supplied, routes the wake to that agent's
    registered service; otherwise defaults to the orchestrator.
    """
    service = _resolve_service(agent_id)
    if service is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No heartbeat service for agent {agent_id!r}"
                if agent_id
                else "Heartbeat service unavailable"
            ),
        )
    try:
        result = await service.run(reason=WakeReason.MANUAL)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Heartbeat failed: {str(e)}",
        )

    return {
        "status": "completed",
        "orchestrator_response": result["orchestrator_response"],
        "actions_taken": result["actions_taken"],
        "tasks_created": result["tasks_created"],
    }
