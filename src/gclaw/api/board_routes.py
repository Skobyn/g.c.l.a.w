"""Board CRUD endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from gclaw.auth.dependencies import get_current_user_id
from gclaw.board.service import BoardService

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
    priority: str = "medium"


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
        priority=req.priority,
        user_id=user_id,
    )
    return task.model_dump(mode="json")
