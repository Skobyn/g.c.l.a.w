"""Cron management and trigger endpoints."""

from __future__ import annotations

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
    title: str
    schedule: str
    assignee: str
    mode: str = "todo"
    description: str = ""
    task_priority: str = "medium"


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
    )
    return cron.model_dump(mode="json")


@router.post("/{cron_id}/trigger")
def trigger_cron(cron_id: str):
    try:
        task = _cron_service.execute(cron_id)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg)
        if "paused" in msg:
            raise HTTPException(status_code=400, detail=msg)
        raise HTTPException(status_code=400, detail=msg)

    return {
        "status": "triggered",
        "cron_id": cron_id,
        "task_id": task.id,
        "task_status": task.status.value,
    }
