"""Onboarding models for the conversational interview flow."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class OnboardingStep(str, Enum):
    """Interview steps in sequence."""

    INTRODUCTION = "introduction"
    COMMUNICATION_STYLE = "communication_style"
    DAILY_ROUTINES = "daily_routines"
    PROFESSIONAL_CONTEXT = "professional_context"
    PERSONAL_CONTEXT = "personal_context"
    INITIAL_CRONS = "initial_crons"
    COMPLETE = "complete"


# Ordered step sequence for progression
STEP_SEQUENCE: list[OnboardingStep] = list(OnboardingStep)


def next_step(current: OnboardingStep) -> OnboardingStep:
    """Return the next step in the sequence, or COMPLETE if at the end."""
    idx = STEP_SEQUENCE.index(current)
    if idx + 1 < len(STEP_SEQUENCE):
        return STEP_SEQUENCE[idx + 1]
    return OnboardingStep.COMPLETE


class OnboardingState(BaseModel):
    """Persistent onboarding state for a user.

    Stored at users/{userId}/profile.onboarding in Firestore.
    """

    user_id: str
    current_step: OnboardingStep = OnboardingStep.INTRODUCTION
    responses: dict[str, str] = Field(default_factory=dict)
    soul_content: str = ""
    completed: bool = False
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_firestore_dict(self) -> dict:
        return self.model_dump(mode="json")

    @classmethod
    def from_firestore_dict(cls, data: dict) -> OnboardingState:
        return cls(**data)
