"""Onboarding service — conversational interview and user-profile generation.

The orchestrator conducts a 10-question interview grounded in validated
psychological frameworks (Big Five / TIPI, Horne-Östberg chronotype,
Self-Determination Theory, Schwartz values, jobs-to-be-done). At the
end, the collected responses are distilled into ``user.md`` — the
shared profile injected into every agent's system prompt.

The distinction from agent soul files: soul = agent personality (how
the agent behaves), user profile = who the user is (what every agent
should know about them).
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from gclaw.models.onboarding import (
    OnboardingState,
    OnboardingStep,
    next_step,
)

if TYPE_CHECKING:
    from google.cloud.firestore import Client as FirestoreClient

    from gclaw.dispatch.runner import AgentRunner
    from gclaw.memory.service import MemoryService

logger = logging.getLogger(__name__)

# Default per-turn timeout for onboarding agent calls. Generous enough
# to accommodate the root orchestrator plus any fallback-chain retries
# plus memory recall, but short enough that a stuck quota error surfaces
# as a clear 503 rather than an indefinite hang.
#
# TODO: The orchestrator is heavy (tool registry, memory recall, routing).
# For simple "ask the user a question" onboarding turns this is overkill
# and needlessly burns model quota. A future improvement is a dedicated
# lightweight onboarding agent (no tools, small model, no memory recall)
# that only conducts the interview.
_DEFAULT_TURN_TIMEOUT_S = 90.0

# System prompts for each interview step. Each tells the orchestrator
# what to ask next; the orchestrator translates into its own voice so
# the interview feels conversational, not scripted. The underlying
# design is research-backed — see models/onboarding.py docstring.
_STEP_PROMPTS: dict[OnboardingStep, str] = {
    OnboardingStep.INTRODUCTION: (
        "You are onboarding a new user to GClaw, their personal AI "
        "assistant. Greet them briefly and warmly. Explain that you'd "
        "like to ask 10 short questions to personalize how every agent "
        "in the system interacts with them — the answers populate a "
        "shared profile, not stored anywhere external. Mention this "
        "is a one-time setup (~3 minutes) and they can skip any "
        "question. Ask if they're ready to start."
    ),
    OnboardingStep.Q1_IDENTITY: (
        "Question 1 of 10 — Identity. Ask: what should I call you, "
        "what do you do, and what's the domain that takes up most of "
        "your work brain? Invite a single sentence — don't probe yet."
    ),
    OnboardingStep.Q2_CHRONOTYPE: (
        "Question 2 of 10 — Chronotype and working hours. Ask: what "
        "timezone are you usually in, and when is your 'sharp-edge' "
        "time — morning, afternoon, late night? (This is grounded in "
        "the Horne-Östberg morningness-eveningness research; don't "
        "cite that — just ask the plain question.)"
    ),
    OnboardingStep.Q3_DETAIL_LEVEL: (
        "Question 3 of 10 — Detail level. Ask: when you ask me "
        "something complex, which shape do you want back? "
        "(a) the bottom line in one sentence, then details only if "
        "you ask; (b) a short summary with key reasoning; "
        "(c) the full context so you can reason alongside me."
    ),
    OnboardingStep.Q4_DIRECTNESS: (
        "Question 4 of 10 — Directness. Ask: when I give you feedback "
        "or pushback, should I be blunt ('that's a bad idea because X'), "
        "soften it ('have you considered Y?'), or somewhere in between? "
        "A 1–5 scale is fine if they prefer that."
    ),
    OnboardingStep.Q5_AUTONOMY: (
        "Question 5 of 10 — Autonomy. Explain: I'll often hit tasks "
        "where there's an obvious reasonable default — e.g. you ask "
        "me to reply to an email, and I can either draft it for your "
        "review or send it straight. On a 1–5 scale, where 1 = always "
        "ask first, 5 = just do the sensible thing and tell me after, "
        "where are you? Invite nuance (e.g. 'depends on reversibility')."
    ),
    OnboardingStep.Q6_INTERRUPTS: (
        "Question 6 of 10 — Interruption tolerance. Ask: when I spot "
        "something important while you're heads-down — inbox emergency, "
        "deadline shift, a task blocker — should I interrupt you, or "
        "queue it for when you next surface?"
    ),
    OnboardingStep.Q7_DISAGREEMENT: (
        "Question 7 of 10 — Disagreement style. Ask: when I think "
        "you're wrong about something, which do you want? "
        "(a) point it out clearly; (b) ask a question that makes you "
        "re-check your own thinking; (c) just do what you asked; "
        "(d) depends on how risky the call is. Invite them to combine."
    ),
    OnboardingStep.Q8_CURRENT_FOCUS: (
        "Question 8 of 10 — Current focus. Ask: what 2–3 projects or "
        "priorities are owning most of your attention right now? "
        "Short phrases are fine — this anchors future suggestions."
    ),
    OnboardingStep.Q9_HARD_NOS: (
        "Question 9 of 10 — Hard-nos. Ask: what kind of task, tone, "
        "or output drains you or that I should never do? Think: the "
        "behavior that would make you wish you'd never turned me on."
    ),
    OnboardingStep.Q10_LATENT_WISH: (
        "Question 10 of 10 — Latent wish. Ask: if you had a perfectly "
        "competent chief-of-staff, what's the one thing you'd want "
        "them to do without ever being asked? Thank them for finishing "
        "the interview and let them know the profile is being compiled."
    ),
}

_USER_PROFILE_GENERATION_PROMPT = """\
You are compiling a shared user-profile markdown document from a \
10-question onboarding interview. This document becomes ``user.md`` \
and is injected into every agent's system prompt as "# About the \
User" — so every word should be actionable context about *who this \
person is*, not about *how the agent behaves*.

Structure the output with these sections (omit a section if the \
answers don't support it — don't invent):

## Identity
# Name, role, domain of focus (from Q1).

## Working style
# Timezone and sharp-edge hours (from Q2). Keep it concrete.

## Communication preferences
# Detail level, tone/directness (from Q3, Q4). Use clear directives
# like "Default to the bottom line first; expand only on request"
# rather than descriptive prose.

## Autonomy & escalation
# When to act vs ask, interrupt vs queue, how to challenge (Q5, Q6, Q7).

## Context agents should carry
# Current projects and priorities (Q8).

## Hard-nos
# Things to never do; drains to avoid (Q9).

## What the user most wants
# The latent wish, framed as an opportunity agents should watch for (Q10).

Rules:
- Write in third person ("The user prefers…" NOT "I prefer…").
- Be specific and directive. Avoid hedges like "seems to" or "maybe".
- Never fabricate — if a question was skipped or vague, drop the
  corresponding bullet rather than guess.
- Output ONLY the markdown document, no preamble.

Interview responses:
{responses}
"""


class OnboardingService:
    """Manages the conversational onboarding interview flow.

    The orchestrator agent conducts the interview. This service
    tracks progress, stores responses, and triggers soul generation.
    """

    def __init__(
        self,
        db: FirestoreClient,
        agent_runner: AgentRunner,
        memory_service: MemoryService | None = None,
        turn_timeout_s: float = _DEFAULT_TURN_TIMEOUT_S,
        user_profile_path: str | None = None,
    ) -> None:
        self._db = db
        self._agent_runner = agent_runner
        self._memory_service = memory_service
        self._turn_timeout_s = turn_timeout_s
        # Where the generated user.md is written on completion. When
        # None, the service writes to ``<GCLAW_CONFIG_DIR>/user.md`` if
        # that env var is set, otherwise skips disk writes (the
        # profile still lives in Firestore onboarding state). Cloud
        # Run's filesystem is ephemeral per revision, so durability
        # depends on the Firestore copy, not the disk file.
        if user_profile_path is None:
            cfg_dir = os.environ.get("GCLAW_CONFIG_DIR")
            user_profile_path = (
                os.path.join(cfg_dir, "user.md") if cfg_dir else None
            )
        self._user_profile_path = user_profile_path

    async def _run_with_timeout(self, **kwargs):
        """Invoke agent_runner.run with a wall-clock timeout.

        Converts an asyncio.TimeoutError into a RuntimeError with a clear
        message — the onboarding route handler turns that into a 503.
        """
        try:
            return await asyncio.wait_for(
                self._agent_runner.run(**kwargs),
                timeout=self._turn_timeout_s,
            )
        except asyncio.TimeoutError as e:
            raise RuntimeError(
                f"Onboarding turn timed out after {self._turn_timeout_s:.0f}s "
                "— likely model quota exhaustion or upstream stall. "
                "Try again in a minute or check Vertex AI quota."
            ) from e

    def _profile_ref(self, user_id: str):
        return (
            self._db.collection("users")
            .document(user_id)
        )

    async def _get_state(self, user_id: str) -> OnboardingState | None:
        """Load onboarding state from Firestore."""
        doc = self._profile_ref(user_id).get()
        if not doc.exists:
            return None
        data = doc.to_dict()
        onboarding_data = data.get("onboarding")
        if onboarding_data is None:
            return None
        return OnboardingState.from_firestore_dict(onboarding_data)

    async def _save_state(self, state: OnboardingState) -> None:
        """Persist onboarding state to Firestore."""
        self._profile_ref(state.user_id).set(
            {"onboarding": state.to_firestore_dict()},
            merge=True,
        )

    async def start_onboarding(self, user_id: str) -> dict:
        """Start or resume the onboarding interview.

        Returns:
            Dict with 'step' and 'message' keys.
        """
        existing = await self._get_state(user_id)
        if existing is not None and not existing.completed:
            # Resume from current step
            step = existing.current_step
            prompt = _STEP_PROMPTS.get(step, "")
            result = await self._run_with_timeout(
                user_id=user_id,
                message=prompt,
                session_id=f"onboarding_{user_id}",
            )
            return {
                "step": step.value,
                "message": result.text,
                "completed": False,
            }

        if existing is not None and existing.completed:
            return {
                "step": "complete",
                "message": "Onboarding already completed.",
                "completed": True,
            }

        # Create new onboarding state
        state = OnboardingState(user_id=user_id)
        await self._save_state(state)

        # Get introduction from orchestrator
        prompt = _STEP_PROMPTS[OnboardingStep.INTRODUCTION]
        result = await self._run_with_timeout(
            user_id=user_id,
            message=prompt,
            session_id=f"onboarding_{user_id}",
        )
        return {
            "step": "introduction",
            "message": result.text,
            "completed": False,
        }

    async def advance_onboarding(
        self,
        user_id: str,
        response: str,
    ) -> dict:
        """Process user response and advance to the next interview step.

        The user's response is stored, then the orchestrator is invoked
        with the next step's prompt to generate the next question.

        Args:
            user_id: The user being onboarded.
            response: The user's response to the current step.

        Returns:
            Dict with 'step', 'message', and 'completed' keys.
        """
        state = await self._get_state(user_id)
        if state is None:
            return await self.start_onboarding(user_id)

        if state.completed:
            return {
                "step": "complete",
                "message": "Onboarding already completed.",
                "completed": True,
            }

        # Store the response for the current step
        state.responses[state.current_step.value] = response

        # Advance to next step
        new_step = next_step(state.current_step)
        state.current_step = new_step
        state.updated_at = datetime.now(timezone.utc)

        if new_step == OnboardingStep.COMPLETE:
            # Compile user.md profile from all responses
            profile_content = await self._generate_user_profile(
                user_id, state.responses
            )
            state.user_profile_content = profile_content
            state.completed = True
            await self._save_state(state)
            return {
                "step": "complete",
                "message": (
                    "Onboarding complete. Your shared user profile "
                    "(user.md) has been compiled and is now injected "
                    "into every agent's prompt."
                ),
                "completed": True,
                "user_profile_preview": profile_content[:500],
            }

        await self._save_state(state)

        # Get next question from orchestrator
        prompt = _STEP_PROMPTS.get(new_step, "")
        context = f"User's previous response: {response}\n\n{prompt}"
        result = await self._run_with_timeout(
            user_id=user_id,
            message=context,
            session_id=f"onboarding_{user_id}",
        )
        return {
            "step": new_step.value,
            "message": result.text,
            "completed": False,
        }

    async def _generate_user_profile(
        self,
        user_id: str,
        responses: dict[str, str],
    ) -> str:
        """Compile ``user.md`` markdown from the 10-question interview.

        Runs the collected responses through the orchestrator with a
        template prompt that forces a structured, third-person profile
        suitable for direct injection into agent system prompts.

        Best-effort writes the content to
        ``<GCLAW_CONFIG_DIR>/user.md`` so the loader picks it up on
        the next prompt build. Disk write failures are non-fatal —
        the profile always persists in Firestore onboarding state.
        """
        formatted_responses = "\n\n".join(
            f"**{step}:** {answer}"
            for step, answer in responses.items()
        )
        prompt = _USER_PROFILE_GENERATION_PROMPT.format(
            responses=formatted_responses
        )

        result = await self._run_with_timeout(
            user_id=user_id,
            message=prompt,
            session_id=f"onboarding_{user_id}_profile",
        )
        profile_content = result.text.strip()

        # Mirror to disk so ConfigLoader.load_user_profile() picks it
        # up on the next request in this revision. Non-fatal: the
        # Firestore onboarding state is the canonical copy.
        if self._user_profile_path:
            try:
                with open(self._user_profile_path, "w") as f:
                    f.write(profile_content)
                logger.info(
                    "onboarding: wrote generated user profile to %s (%d bytes)",
                    self._user_profile_path,
                    len(profile_content),
                )
            except Exception:
                logger.warning(
                    "onboarding: failed to write user profile to %s",
                    self._user_profile_path,
                    exc_info=True,
                )

        # Capture to Memory Bank so evolving preferences can later
        # supplement the static profile.
        if self._memory_service is not None:
            try:
                await self._memory_service.capture(
                    user_id=user_id,
                    conversation_text=(
                        "Onboarding interview completed. Generated "
                        f"user profile:\n\n{profile_content}"
                    ),
                    topics=["USER_PREFERENCES", "EXPLICIT_INSTRUCTIONS"],
                )
            except Exception:
                logger.warning(
                    "Failed to capture user profile to memory bank for %s",
                    user_id,
                    exc_info=True,
                )

        return profile_content

    async def get_status(self, user_id: str) -> dict:
        """Get onboarding completion status.

        Returns:
            Dict with 'completed', 'current_step', and 'progress' keys.
        """
        state = await self._get_state(user_id)
        if state is None:
            return {
                "completed": False,
                "current_step": None,
                "progress": 0.0,
            }

        total_steps = len(OnboardingStep) - 1  # exclude COMPLETE
        if state.completed:
            return {
                "completed": True,
                "current_step": "complete",
                "progress": 1.0,
            }

        current_idx = list(OnboardingStep).index(state.current_step)
        return {
            "completed": False,
            "current_step": state.current_step.value,
            "progress": current_idx / total_steps,
        }
