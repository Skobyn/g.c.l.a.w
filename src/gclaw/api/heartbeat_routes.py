"""Heartbeat trigger endpoint.

Cloud Scheduler hits POST /heartbeat to wake the orchestrator's
consciousness loop. This is not a health check — it triggers the
orchestrator to scan the world state and decide what to do.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from gclaw.heartbeat.service import HeartbeatService

router = APIRouter()

_heartbeat_service: HeartbeatService | None = None


def init_heartbeat_router(heartbeat_service: HeartbeatService) -> APIRouter:
    global _heartbeat_service
    _heartbeat_service = heartbeat_service
    return router


@router.post("/heartbeat")
async def trigger_heartbeat():
    """Trigger a heartbeat cycle.

    Called by Cloud Scheduler at a configurable interval (default: 15 min).
    The orchestrator gathers context, reasons about what needs attention,
    and takes action (create tasks, notify user, or go back to sleep).
    """
    try:
        result = await _heartbeat_service.run()
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
