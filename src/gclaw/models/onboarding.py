"""Onboarding models for the conversational interview flow.

The 10-question interview is grounded in validated psychological
frameworks:

- Q2 chronotype: Horne-Östberg Morningness-Eveningness Questionnaire.
- Q3/Q4 communication style: Gosling et al. TIPI (Ten-Item Personality
  Inventory), mapping to Big Five Agreeableness/Conscientiousness.
- Q5 autonomy preference: Deci & Ryan Self-Determination Theory
  (autonomy vs. dependence on external confirmation).
- Q7 disagreement style: Schwartz Theory of Basic Human Values
  (benevolence vs. stimulation trade-offs).
- Q10 latent-wish: classic jobs-to-be-done interviewing
  (Christensen), which surfaces unmet needs better than
  feature-preference questions.

We ask one question at a time. Research on self-disclosure (Aron et
al. 1997, "36 Questions That Lead to Closeness") shows gradual,
specific prompts surface more honest preferences than a single bulk
survey.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class OnboardingStep(str, Enum):
    """Interview steps in sequence."""

    INTRODUCTION = "introduction"
    Q1_IDENTITY = "q1_identity"
    Q2_CHRONOTYPE = "q2_chronotype"
    Q3_DETAIL_LEVEL = "q3_detail_level"
    Q4_DIRECTNESS = "q4_directness"
    Q5_AUTONOMY = "q5_autonomy"
    Q6_INTERRUPTS = "q6_interrupts"
    Q7_DISAGREEMENT = "q7_disagreement"
    Q8_CURRENT_FOCUS = "q8_current_focus"
    Q9_HARD_NOS = "q9_hard_nos"
    Q10_LATENT_WISH = "q10_latent_wish"
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
    # Generated ``user.md`` content — the shared user profile injected
    # into every agent's system prompt. Legacy state docs stored this
    # under ``soul_content``; from_firestore_dict() maps that forward.
    user_profile_content: str = ""
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
        data = dict(data)
        # Legacy compat: older state docs stored the generated profile
        # under ``soul_content`` and used retired step names.
        if "soul_content" in data and "user_profile_content" not in data:
            data["user_profile_content"] = data.pop("soul_content")
        step_raw = data.get("current_step")
        valid = {s.value for s in OnboardingStep}
        if step_raw is not None and step_raw not in valid:
            data["current_step"] = OnboardingStep.INTRODUCTION.value
        allowed = set(cls.model_fields.keys())
        return cls(**{k: v for k, v in data.items() if k in allowed})
