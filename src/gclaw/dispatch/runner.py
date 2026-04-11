"""Run agent turns via ADK Runner.

Memory hooks (auto-recall / auto-capture) wrap the outer-most turn.
All model execution — Gemini and non-Gemini alike — flows through ADK's
native Runner; non-Gemini providers are handled by wrapping their models
with google.adk.models.lite_llm.LiteLlm at agent construction time.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService
from google.genai import types

if TYPE_CHECKING:
    from gclaw.memory.service import MemoryService

logger = logging.getLogger(__name__)


@dataclass
class AgentResponse:
    """Response from a single agent turn."""

    text: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    is_final: bool = False


class AgentRunner:
    """Wraps ADK Runner for executing agent turns.

    When a MemoryService is provided:
    - Before each turn: auto-recall relevant memories
    - After each turn: auto-capture facts from the exchange (fire-and-forget)
    """

    def __init__(
        self,
        agent: LlmAgent,
        app_name: str,
        session_service: BaseSessionService,
        memory_service: "MemoryService | None" = None,
        board_service: object | None = None,
    ) -> None:
        self._agent = agent
        self._app_name = app_name
        self._session_service = session_service
        self._memory_service = memory_service
        self._board_service = board_service
        self._pending_captures: set[asyncio.Task] = set()
        self._runner = Runner(
            agent=agent,
            app_name=app_name,
            session_service=session_service,
        )

    async def run(
        self,
        user_id: str,
        session_id: str,
        message: str,
    ) -> AgentResponse:
        """Execute a single user turn with memory hooks."""
        if self._board_service is not None:
            self._board_service.set_active_user(user_id)

        recalled_text = ""
        if self._memory_service is not None:
            try:
                memories = await self._memory_service.recall(
                    user_id=user_id,
                    query=message,
                    agent_id=self._agent.name,
                    merge_user_scope=True,
                )
                if memories:
                    recalled_text = self._memory_service.format_for_prompt(memories)
            except Exception:
                logger.warning(
                    "Memory recall failed for user %s, proceeding without memories",
                    user_id,
                    exc_info=True,
                )

        full_message = (
            f"[Recalled memories]\n{recalled_text}\n\n[User message]\n{message}"
            if recalled_text
            else message
        )

        try:
            session = await self._session_service.get_session(
                app_name=self._app_name,
                user_id=user_id,
                session_id=session_id,
            )
            if session is None:
                await self._session_service.create_session(
                    app_name=self._app_name,
                    user_id=user_id,
                    session_id=session_id,
                )
        except Exception:
            try:
                await self._session_service.create_session(
                    app_name=self._app_name,
                    user_id=user_id,
                    session_id=session_id,
                )
            except Exception:
                pass

        content = types.Content(
            role="user",
            parts=[types.Part(text=full_message)],
        )

        response = AgentResponse()
        async for event in self._runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=content,
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        response.text += part.text
                    if part.function_call:
                        response.tool_calls.append({
                            "name": part.function_call.name,
                            "args": dict(part.function_call.args or {}),
                        })
            if event.is_final_response():
                response.is_final = True

        if self._memory_service is not None and response.text:
            conversation_text = f"User: {message}\nAgent: {response.text}"
            task = asyncio.create_task(
                self._memory_service.capture(
                    user_id=user_id,
                    conversation_text=conversation_text,
                )
            )
            self._pending_captures.add(task)
            task.add_done_callback(self._pending_captures.discard)

        return response

    async def end_session(self, user_id: str, session_id: str) -> None:
        """End-of-session hook: extract memories from the full transcript.

        Reads the ADK session, concatenates user + assistant events into a
        transcript, and invokes the heavier generate_memories extraction.
        Errors are logged and suppressed; end-of-session should not fail loudly.
        """
        if self._memory_service is None:
            return

        try:
            session = await self._session_service.get_session(
                app_name=self._app_name,
                user_id=user_id,
                session_id=session_id,
            )
        except Exception:
            logger.warning(
                "end_session: could not load ADK session %s",
                session_id,
                exc_info=True,
            )
            return
        if session is None:
            return

        transcript_lines: list[str] = []
        for event in getattr(session, "events", []) or []:
            content = getattr(event, "content", None)
            if content is None or not getattr(content, "parts", None):
                continue
            role = getattr(content, "role", "user") or "user"
            label = "User" if role == "user" else "Agent"
            for part in content.parts:
                text = getattr(part, "text", None)
                if text:
                    transcript_lines.append(f"{label}: {text}")
        if not transcript_lines:
            return

        try:
            await self._memory_service.generate_memories(
                user_id=user_id,
                conversation_text="\n".join(transcript_lines),
            )
        except Exception:
            logger.warning(
                "end_session: generate_memories failed for %s",
                user_id,
                exc_info=True,
            )
