"""Run agent turns via ADK Runner.

Memory hooks (auto-recall / auto-capture) wrap the outer-most turn.
All model execution — Gemini and non-Gemini alike — flows through ADK's
native Runner; non-Gemini providers are handled by wrapping their models
with google.adk.models.lite_llm.LiteLlm at agent construction time.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService
from google.genai import types

from gclaw.models.memory import DEFAULT_EXTRACTION_TOPICS

if TYPE_CHECKING:
    from gclaw.memory.service import MemoryService
    from gclaw.session.service import SessionService
    from gclaw.usage.recorder import UsageRecorder

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
        session_store: "SessionService | None" = None,
        extraction_topics: list[str] | None = None,
        usage_recorder: "UsageRecorder | None" = None,
    ) -> None:
        self._agent = agent
        self._app_name = app_name
        self._session_service = session_service
        self._memory_service = memory_service
        self._board_service = board_service
        self._session_store = session_store
        self._usage_recorder = usage_recorder
        # Default to the full MemoryTopic taxonomy so Memory Bank's
        # generate call has structured guidance instead of picking a
        # narrow category on its own. Callers can override with a
        # custom list (e.g. just `["USER_PREFERENCES"]` for a lean
        # capture path) or pass [] to opt out entirely.
        self._extraction_topics: list[str] = (
            list(extraction_topics)
            if extraction_topics is not None
            else list(DEFAULT_EXTRACTION_TOPICS)
        )
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
        if self._session_store is not None:
            self._session_store.set_active_user(user_id)

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
        turn_start = time.perf_counter()
        run_error: str | None = None
        tokens_in_total = 0
        tokens_out_total = 0
        model_seen: str | None = None
        try:
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
                um = getattr(event, "usage_metadata", None)
                if um is not None:
                    tokens_in_total += (
                        getattr(um, "prompt_token_count", 0) or 0
                    )
                    tokens_out_total += (
                        getattr(um, "candidates_token_count", 0) or 0
                    )
                mv = getattr(event, "model_version", None)
                if mv and model_seen is None:
                    model_seen = mv
                if event.is_final_response():
                    response.is_final = True
        except Exception as e:  # noqa: BLE001 — record + re-raise
            run_error = f"{type(e).__name__}: {e}"
            self._record_turn(
                user_id=user_id,
                session_id=session_id,
                start=turn_start,
                success=False,
                error=run_error,
                tokens_in=tokens_in_total,
                tokens_out=tokens_out_total,
                model_seen=model_seen,
                tool_calls=response.tool_calls,
            )
            raise

        self._record_turn(
            user_id=user_id,
            session_id=session_id,
            start=turn_start,
            success=True,
            error=None,
            tokens_in=tokens_in_total,
            tokens_out=tokens_out_total,
            model_seen=model_seen,
            tool_calls=response.tool_calls,
        )

        if self._session_store is not None and response.text:
            try:
                if self._session_store.get_or_none(session_id) is None:
                    self._session_store.create_with_id(
                        session_id=session_id,
                        user_id=user_id,
                    )
                self._session_store.append_message(
                    session_id=session_id, role="user", content=message
                )
                self._session_store.append_message(
                    session_id=session_id,
                    role="agent",
                    content=response.text,
                )
            except Exception:
                logger.warning(
                    "session_store mirror failed for %s, continuing",
                    session_id,
                    exc_info=True,
                )

        if self._memory_service is not None and response.text:
            conversation_text = f"User: {message}\nAgent: {response.text}"
            task = asyncio.create_task(
                self._memory_service.capture(
                    user_id=user_id,
                    conversation_text=conversation_text,
                    topics=self._extraction_topics or None,
                )
            )
            self._pending_captures.add(task)
            task.add_done_callback(self._pending_captures.discard)

        return response

    def _record_turn(
        self,
        *,
        user_id: str,
        session_id: str,
        start: float,
        success: bool,
        error: str | None,
        tokens_in: int,
        tokens_out: int,
        model_seen: str | None,
        tool_calls: list[dict],
    ) -> None:
        """Best-effort telemetry emission. Never raises."""
        recorder = self._usage_recorder
        if recorder is None or not getattr(recorder, "enabled", False):
            return
        duration_ms = int((time.perf_counter() - start) * 1000)
        agent_name = getattr(self._agent, "name", "agent") or "agent"
        try:
            recorder.record_agent_invoke(
                agent_name=agent_name,
                caller=None,
                duration_ms=duration_ms,
                success=success,
                error=error,
                user_id=user_id,
                session_id=session_id,
                metadata={"tool_call_count": len(tool_calls)},
            )
            if tokens_in or tokens_out or model_seen:
                recorder.record_model_call(
                    model_id=model_seen or "unknown",
                    provider_id=None,
                    tokens_in=tokens_in or None,
                    tokens_out=tokens_out or None,
                    cost_usd=None,
                    duration_ms=duration_ms,
                    success=success,
                    error=error,
                    user_id=user_id,
                    session_id=session_id,
                    caller=agent_name,
                    metadata={
                        "token_source": (
                            "adk_usage_metadata"
                            if (tokens_in or tokens_out)
                            else "none"
                        ),
                    },
                )
            for call in tool_calls:
                recorder.record_tool_call(
                    tool_name=call.get("name") or "unknown",
                    agent_name=agent_name,
                    duration_ms=0,
                    success=True,
                    user_id=user_id,
                    session_id=session_id,
                    metadata={"args_keys": sorted(
                        list((call.get("args") or {}).keys())
                    )},
                )
        except Exception:
            logger.warning("usage: _record_turn failed", exc_info=True)

    async def run_trace(
        self,
        user_id: str,
        session_id: str,
        message: str,
    ) -> tuple[AgentResponse, str | None]:
        """Eval-only variant of `run()` that captures partial responses.

        `run()` re-raises any exception that happens while draining the ADK
        event stream — which means tool-execution errors (e.g. `ValueError:
        Task t7 not found`) throw away the tool_calls we already observed
        upstream in the same turn. For the routing eval we specifically
        want to know which tool the orchestrator chose, independent of
        whether the tool actually succeeded.

        Returns `(response, error)`. `error` is None on a clean run or a
        stringified exception if the event stream aborted. `response`
        always carries whatever events were drained before the abort.

        Production code should keep calling `run()` — this method exists
        solely for `gclaw.eval`.
        """
        # Pre-turn hooks — must match run() so board/session tools
        # have a user context when they fire.
        if self._board_service is not None:
            self._board_service.set_active_user(user_id)
        if self._session_store is not None:
            self._session_store.set_active_user(user_id)

        try:
            session = await self._session_service.get_session(
                app_name=self._app_name, user_id=user_id, session_id=session_id,
            )
            if session is None:
                await self._session_service.create_session(
                    app_name=self._app_name, user_id=user_id, session_id=session_id,
                )
        except Exception:
            try:
                await self._session_service.create_session(
                    app_name=self._app_name, user_id=user_id, session_id=session_id,
                )
            except Exception:
                pass

        content = types.Content(
            role="user",
            parts=[types.Part(text=message)],
        )

        response = AgentResponse()
        error: str | None = None
        try:
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
        except Exception as e:
            error = f"{type(e).__name__}: {e}"

        return response, error

    async def end_session(self, user_id: str, session_id: str) -> None:
        """End-of-session hook: extract memories from the full transcript.

        When a persistent `session_store` is configured, delegate to its
        `end_session` — it reads from Firestore and already invokes
        `memory_service.generate_memories` internally. Otherwise fall back
        to reading the ADK in-memory session and invoking generate_memories
        directly.

        Errors are logged and suppressed; end-of-session should not fail loudly.
        """
        if self._session_store is not None:
            try:
                await self._session_store.end_session(session_id)
            except Exception:
                logger.warning(
                    "end_session: session_store.end_session failed for %s",
                    session_id,
                    exc_info=True,
                )
            return

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
