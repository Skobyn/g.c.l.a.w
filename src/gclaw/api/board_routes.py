"""Board CRUD endpoints."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from gclaw.auth.dependencies import get_current_user_id
from gclaw.board.service import BoardService
from gclaw.board.transitions import TransitionNotAllowed
from gclaw.models.task import TaskPriority, TaskStatus

router = APIRouter(prefix="/board")

_board_service: BoardService | None = None


def init_board_router(board_service: BoardService) -> APIRouter:
    global _board_service
    _board_service = board_service
    return router


class CreateTaskRequest(BaseModel):
    title: str
    assignee: str
    description: str = ""
    priority: Literal["high", "medium", "low"] = "medium"
    initial_status: Literal["backlog", "queued"] = "queued"
    requires_approval: bool = False
    dependencies: list[str] = Field(default_factory=list)


class MoveStatusRequest(BaseModel):
    target: TaskStatus


class ApproveRequest(BaseModel):
    note: str | None = None


class RejectRequest(BaseModel):
    note: str = Field(..., min_length=1)


@router.get("/tasks")
def list_tasks(user_id: str = Depends(get_current_user_id)):
    tasks = _board_service.get_all_tasks(user_id=user_id)
    return [t.model_dump(mode="json") for t in tasks]


@router.post("/tasks", status_code=201)
def create_task(
    req: CreateTaskRequest,
    user_id: str = Depends(get_current_user_id),
):
    task = _board_service.create_task(
        title=req.title,
        assignee=req.assignee,
        description=req.description,
        priority=TaskPriority(req.priority),
        status=TaskStatus(req.initial_status),
        dependencies=req.dependencies,
        requires_approval=req.requires_approval,
        source_type="user",
        source_origin=user_id,
        user_id=user_id,
    )
    return task.model_dump(mode="json")


@router.post("/tasks/{task_id}/status")
def move_status(
    task_id: str,
    req: MoveStatusRequest,
    user_id: str = Depends(get_current_user_id),
):
    try:
        task = _board_service.move_status(
            task_id, req.target, user_id=user_id
        )
    except TransitionNotAllowed as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return task.model_dump(mode="json")


@router.post("/tasks/{task_id}/approve")
def approve_task(
    task_id: str,
    req: ApproveRequest | None = None,
    user_id: str = Depends(get_current_user_id),
):
    note = req.note if req is not None else None
    try:
        task = _board_service.approve(task_id, user_id=user_id, note=note)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=409, detail=msg)
    return task.model_dump(mode="json")


@router.post("/tasks/{task_id}/reject")
def reject_task(
    task_id: str,
    req: RejectRequest,
    user_id: str = Depends(get_current_user_id),
):
    try:
        task = _board_service.reject(task_id, user_id=user_id, note=req.note)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=409, detail=msg)
    return task.model_dump(mode="json")
