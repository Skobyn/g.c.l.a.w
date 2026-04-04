"""Run agent turns via ADK Runner or RemoteRunner."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService
from google.genai import types

if TYPE_CHECKING:
    from gclaw.dispatch.remote_runner import RemoteRunner
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

    When a RemoteRunner is provided, uses it instead of ADK Runner.
    This enables non-Gemini models (Nemotron via OpenRouter, etc.)
    that can't run through ADK natively.

    When a MemoryService is provided:
    - Before each turn: auto-recall relevant memories
    - After each turn: auto-capture facts from the exchange (fire-and-forget)
    """

    def __init__(
        self,
        agent: LlmAgent,
        app_name: str,
        session_service: BaseSessionService,
        memory_service: MemoryService | None = None,
        remote_runner: RemoteRunner | None = None,
    ) -> None:
        self._agent = agent
        self._app_name = app_name
        self._session_service = session_service
        self._memory_service = memory_service
        self._remote_runner = remote_runner
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
        # 1. Auto-recall memories
        recalled_text = ""
        if self._memory_service is not None:
            try:
                memories = await self._memory_service.recall(
                    user_id=user_id,
                    query=message,
                )
                if memories:
                    recalled_text = self._memory_service.format_for_prompt(memories)
            except Exception:
                logger.warning(
                    "Memory recall failed for user %s, proceeding without memories",
                    user_id,
                    exc_info=True,
                )

        if recalled_text:
            full_message = (
                f"[Recalled memories]\n{recalled_text}\n\n"
                f"[User message]\n{message}"
            )
        else:
            full_message = message

        # 2. Execute via remote runner or ADK
        if self._remote_runner is not None:
            response = await self._run_remote(full_message)
        else:
            response = await self._run_adk(user_id, session_id, full_message)

        # 3. Auto-capture memories (fire-and-forget)
        if self._memory_service is not None and response.text:
            try:
                conversation_text = f"User: {message}\nAgent: {response.text}"
                await self._memory_service.capture(
                    user_id=user_id,
                    conversation_text=conversation_text,
                )
            except Exception:
                logger.warning(
                    "Memory capture failed for user %s, continuing",
                    user_id,
                    exc_info=True,
                )

        return response

    async def _run_remote(self, message: str) -> AgentResponse:
        """Execute via RemoteRunner (OpenAI-compatible API)."""
        text = await self._remote_runner.generate(
            system_prompt=self._agent.instruction,
            message=message,
        )
        return AgentResponse(text=text, is_final=True)

    async def _run_adk(
        self,
        user_id: str,
        session_id: str,
        full_message: str,
    ) -> AgentResponse:
        """Execute via ADK Runner (Gemini/Gemma models)."""
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

        return response
