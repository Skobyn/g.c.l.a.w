"""API routes for the onboarding interview flow."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from gclaw.auth.dependencies import get_current_user_id
from gclaw.onboarding.service import OnboardingService


class AdvanceRequest(BaseModel):
    response: str


def init_onboarding_router(
    onboarding_service: OnboardingService,
) -> APIRouter:
    router = APIRouter(prefix="/onboarding", tags=["onboarding"])

    @router.post("/start")
    async def start_onboarding(
        user_id: str = Depends(get_current_user_id),
    ):
        try:
            return await onboarding_service.start_onboarding(user_id)
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e))

    @router.post("/advance")
    async def advance_onboarding(
        body: AdvanceRequest,
        user_id: str = Depends(get_current_user_id),
    ):
        try:
            return await onboarding_service.advance_onboarding(
                user_id=user_id,
                response=body.response,
            )
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e))

    @router.get("/status")
    async def onboarding_status(
        user_id: str = Depends(get_current_user_id),
    ):
        return await onboarding_service.get_status(user_id)

    return router
