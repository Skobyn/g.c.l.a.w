"""Cron management and trigger endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from gclaw.cron.service import CronService

router = APIRouter(prefix="/crons")

_cron_service: CronService | None = None


def init_cron_router(cron_service: CronService) -> APIRouter:
    global _cron_service
    _cron_service = cron_service
    return router


class CreateCronRequest(BaseModel):
    """Create-cron payload.

    Accepts both the legacy flat shape (``schedule`` as a cron-expression
    string, no ``payload``) and the new structured shape (``schedule``,
    ``payload``, ``delivery`` as tagged-union dicts).
    """

    title: str
    assignee: str
    schedule: Any  # str (legacy) OR dict {"kind": "at"|"every"|"cron", ...}
    payload: Any | None = None
    delivery: Any | None = None
    failure_alert: Any | None = None
    mode: str = "todo"
    description: str = ""
    task_priority: str = "medium"
    wake_mode: str = "now"
    enabled: bool = True
    delete_after_run: bool = False


@router.get("")
def list_crons():
    crons = _cron_service.list_all()
    return [c.model_dump(mode="json") for c in crons]


@router.post("", status_code=201)
def create_cron(req: CreateCronRequest):
    cron = _cron_service.create(
        title=req.title,
        schedule=req.schedule,
        assignee=req.assignee,
        mode=req.mode,
        description=req.description,
        task_priority=req.task_priority,
        payload=req.payload,
        delivery=req.delivery,
        failure_alert=req.failure_alert,
        wake_mode=req.wake_mode,
        enabled=req.enabled,
        delete_after_run=req.delete_after_run,
    )
    return cron.model_dump(mode="json")


@router.delete("/{cron_id}", status_code=204)
def delete_cron(cron_id: str):
    _cron_service.delete(cron_id)
    return None


@router.post("/{cron_id}/trigger")
async def trigger_cron(cron_id: str):
    try:
        result = await _cron_service.execute(cron_id)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg)
        if "paused" in msg:
            raise HTTPException(status_code=400, detail=msg)
        raise HTTPException(status_code=400, detail=msg)

    # Agent-turn payloads return a BoardTask; system_event returns dict/None.
    if result is None:
        return {"status": "triggered", "cron_id": cron_id}
    if hasattr(result, "id") and hasattr(result, "status"):
        return {
            "status": "triggered",
            "cron_id": cron_id,
            "task_id": result.id,
            "task_status": result.status.value,
        }
    return {"status": "triggered", "cron_id": cron_id, "event": result}
