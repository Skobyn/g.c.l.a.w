"""Board CRUD endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from gclaw.board.service import BoardService

router = APIRouter(prefix="/board")

_board_service: BoardService | None = None


def init_board_router(board_service: BoardService) -> APIRouter:
    global _board_service
    _board_service = board_service
    return router


class CreateTaskRequest(BaseModel):
    user_id: str
    title: str
    assignee: str
    description: str = ""
    priority: str = "medium"


@router.get("/tasks")
def list_tasks(user_id: str = Query(...)):
    tasks = _board_service.get_all_tasks()
    return [t.model_dump(mode="json") for t in tasks]


@router.post("/tasks", status_code=201)
def create_task(req: CreateTaskRequest):
    task = _board_service.create_task(
        title=req.title,
        assignee=req.assignee,
        description=req.description,
        priority=req.priority,
    )
    return task.model_dump(mode="json")
