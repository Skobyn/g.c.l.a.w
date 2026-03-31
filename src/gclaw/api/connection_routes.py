"""API routes for cross-user A2A connections."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from gclaw.auth.dependencies import get_current_user_id
from gclaw.connection.service import ConnectionService
from gclaw.models.connection import ConnectionPermission


class ConnectionRequest(BaseModel):
    to_user_id: str
    permission: str = "read"


class UpdatePermissionRequest(BaseModel):
    permission: str


class CrossUserTaskRequest(BaseModel):
    connection_id: str
    title: str
    assignee: str
    description: str = ""


def init_connection_router(
    connection_service: ConnectionService,
) -> APIRouter:
    router = APIRouter(prefix="/connections", tags=["connections"])

    @router.post("/request")
    def request_connection(
        body: ConnectionRequest,
        user_id: str = Depends(get_current_user_id),
    ):
        try:
            conn = connection_service.request_connection(
                from_user_id=user_id,
                to_user_id=body.to_user_id,
                permission=ConnectionPermission(body.permission),
            )
            return conn.model_dump(mode="json")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/{connection_id}/accept")
    def accept_connection(
        connection_id: str,
        user_id: str = Depends(get_current_user_id),
    ):
        try:
            conn = connection_service.accept_connection(
                user_id=user_id,
                connection_id=connection_id,
            )
            return conn.model_dump(mode="json")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/{connection_id}/reject")
    def reject_connection(
        connection_id: str,
        user_id: str = Depends(get_current_user_id),
    ):
        try:
            conn = connection_service.reject_connection(
                user_id=user_id,
                connection_id=connection_id,
            )
            return conn.model_dump(mode="json")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/{connection_id}/revoke")
    def revoke_connection(
        connection_id: str,
        user_id: str = Depends(get_current_user_id),
    ):
        try:
            conn = connection_service.revoke_connection(
                user_id=user_id,
                connection_id=connection_id,
            )
            return conn.model_dump(mode="json")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/{connection_id}/permission")
    def update_permission(
        connection_id: str,
        body: UpdatePermissionRequest,
        user_id: str = Depends(get_current_user_id),
    ):
        """Update the permission level on an active connection."""
        try:
            conn = connection_service.check_permission(
                user_id=user_id,
                connection_id=connection_id,
                required=ConnectionPermission.READ,
            )
            updated = conn.model_copy(update={
                "permission": ConnectionPermission(body.permission),
            })
            # Update via service (both records)
            from gclaw.firestore.connection_repo import ConnectionRepo
            repo = ConnectionRepo(connection_service._db, user_id)
            repo.update(updated)
            peer_id = (
                conn.to_user_id
                if conn.from_user_id == user_id
                else conn.from_user_id
            )
            peer_repo = ConnectionRepo(connection_service._db, peer_id)
            peer_repo.update(updated)
            return updated.model_dump(mode="json")
        except (ValueError, PermissionError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/task")
    def create_cross_user_task(
        body: CrossUserTaskRequest,
        user_id: str = Depends(get_current_user_id),
    ):
        """Create a task on a connected user's board."""
        try:
            task = connection_service.create_task_for_peer(
                user_id=user_id,
                connection_id=body.connection_id,
                title=body.title,
                assignee=body.assignee,
                description=body.description,
            )
            return task.model_dump(mode="json")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.get("")
    def list_connections(
        user_id: str = Depends(get_current_user_id),
    ):
        conns = connection_service.list_connections(user_id=user_id)
        return [c.model_dump(mode="json") for c in conns]

    @router.get("/incoming")
    def list_incoming(
        user_id: str = Depends(get_current_user_id),
    ):
        conns = connection_service.list_pending_incoming(user_id=user_id)
        return [c.model_dump(mode="json") for c in conns]

    return router
