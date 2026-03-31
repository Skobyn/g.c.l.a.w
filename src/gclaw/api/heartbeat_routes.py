"""Heartbeat trigger endpoint — placeholder until Task 6."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


def init_heartbeat_router(heartbeat_service: object) -> APIRouter:
    return router
