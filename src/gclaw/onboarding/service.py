"""Onboarding service — conversational interview and soul generation.

The onboarding flow is driven by the orchestrator agent. This service
tracks state, stores responses, and triggers soul file generation by
sending the collected interview through the orchestrator.
"""

from __future__ import annotations

import asyncio
import logging
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

# System prompts for each interview step
_STEP_PROMPTS: dict[OnboardingStep, str] = {
    OnboardingStep.INTRODUCTION: (
        "You are onboarding a new user. Introduce yourself as GClaw, "
        "their personal AI assistant. Explain your capabilities briefly "
        "(task management, scheduling, research, smart home, etc.) and "
        "ask if they're ready to get started with a quick interview to "
        "personalize the experience."
    ),
    OnboardingStep.COMMUNICATION_STYLE: (
        "Ask the user about their communication preferences: "
        "Do they prefer casual or formal tone? Concise or detailed responses? "
        "Any specific style preferences (e.g., use of emoji, humor, etc.)?"
    ),
    OnboardingStep.DAILY_ROUTINES: (
        "Ask about the user's daily routines and priorities: "
        "What does a typical day look like? When do they wake up? "
        "What are their most important daily tasks or habits?"
    ),
    OnboardingStep.PROFESSIONAL_CONTEXT: (
        "Ask about the user's professional context: "
        "What is their role? What tools do they use daily? "
        "What workflows could benefit from automation?"
    ),
    OnboardingStep.PERSONAL_CONTEXT: (
        "Ask about personal context: interests, family, smart home setup, "
        "hobbies. Only what they're comfortable sharing — this helps "
        "personalize reminders and suggestions."
    ),
    OnboardingStep.INITIAL_CRONS: (
        "Based on what you've learned, suggest 2-3 initial automated routines "
        "(crons) that would be useful. Examples: morning briefing, inbox triage, "
        "end-of-day summary. Ask the user which ones they'd like to set up."
    ),
}

_SOUL_GENERATION_PROMPT = """\
Based on the following onboarding interview responses, generate a soul \
profile for this user. The soul profile should be a markdown document \
that captures:

- Communication style preferences
- Daily routines and priorities
- Professional context and workflows
- Personal interests and context
- General personality traits and preferences

Format it as a clean markdown document suitable for use as a base soul \
file (soul/base.md). Be specific and actionable — this will be injected \
into agent system prompts.

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
    ) -> None:
        self._db = db
        self._agent_runner = agent_runner
        self._memory_service = memory_service
        self._turn_timeout_s = turn_timeout_s

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
            # Generate soul from all responses
            soul_content = await self._generate_soul(
                user_id, state.responses
            )
            state.soul_content = soul_content
            state.completed = True
            await self._save_state(state)
            return {
                "step": "complete",
                "message": (
                    "Onboarding complete! Your soul profile has been "
                    "generated and saved."
                ),
                "completed": True,
                "soul_preview": soul_content[:500],
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

    async def _generate_soul(
        self,
        user_id: str,
        responses: dict[str, str],
    ) -> str:
        """Generate soul file content from interview responses.

        Sends all collected responses through the orchestrator to
        produce the soul profile markdown.
        """
        formatted_responses = "\n\n".join(
            f"**{step}:** {answer}"
            for step, answer in responses.items()
        )
        prompt = _SOUL_GENERATION_PROMPT.format(
            responses=formatted_responses
        )

        result = await self._run_with_timeout(
            user_id=user_id,
            message=prompt,
            session_id=f"onboarding_{user_id}_soul",
        )
        soul_content = result.text

        # Capture soul content to Memory Bank
        if self._memory_service is not None:
            try:
                await self._memory_service.capture(
                    user_id=user_id,
                    conversation_text=(
                        f"Onboarding interview completed. "
                        f"Soul profile generated:\n\n{soul_content}"
                    ),
                    topics=["USER_PREFERENCES", "EXPLICIT_INSTRUCTIONS"],
                )
            except Exception:
                logger.warning(
                    "Failed to capture soul to memory bank for %s",
                    user_id,
                    exc_info=True,
                )

        return soul_content

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
