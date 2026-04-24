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
from copy import copy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService
from google.genai import types
from opentelemetry import trace

from gclaw.models.memory import DEFAULT_EXTRACTION_TOPICS
from gclaw.observability.semconv import set_llm_attrs, set_turn_attrs

if TYPE_CHECKING:
    from gclaw.memory.service import MemoryService
    from gclaw.session.service import SessionService
    from gclaw.usage.recorder import UsageRecorder

logger = logging.getLogger(__name__)
_tracer = trace.get_tracer(__name__)


def _is_retryable_model_error(exc: BaseException) -> bool:
    """Return True for errors that warrant trying the next fallback model.

    Narrowly scoped to transport- and provider-capacity-level failures that
    might succeed on a different model. Excludes programming errors and
    anything that clearly won't be fixed by swapping models.
    """
    # Never retry these — different model won't help.
    if isinstance(exc, (ValueError, TypeError, KeyError, AttributeError)):
        return False
    try:
        from pydantic import ValidationError
        if isinstance(exc, ValidationError):
            return False
    except Exception:
        pass

    # Generic transport-level errors.
    if isinstance(exc, (TimeoutError, ConnectionError, asyncio.TimeoutError)):
        return True

    # google-api-core exceptions — capacity, availability, deadlines, quota.
    try:
        from google.api_core import exceptions as gapi_exc
        retryable_gapi = (
            gapi_exc.ResourceExhausted,
            gapi_exc.ServiceUnavailable,
            gapi_exc.InternalServerError,
            gapi_exc.DeadlineExceeded,
            gapi_exc.PermissionDenied,  # billing / quota denial
            gapi_exc.TooManyRequests,
            gapi_exc.BadGateway,
            gapi_exc.GatewayTimeout,
        )
        if isinstance(exc, retryable_gapi):
            return True
    except Exception:
        pass

    # google-genai SDK errors — different class hierarchy from google-api-core.
    # ClientError wraps 4xx responses; carries .code (HTTP status int) and
    # .status (string like "RESOURCE_EXHAUSTED"). ServerError wraps 5xx.
    try:
        from google.genai import errors as genai_errors
        if isinstance(exc, genai_errors.ServerError):
            return True
        if isinstance(exc, genai_errors.ClientError):
            code = getattr(exc, "code", None)
            status = (getattr(exc, "status", None) or "").upper()
            if code in (429, 503, 504) or status in (
                "RESOURCE_EXHAUSTED",
                "SERVICE_UNAVAILABLE",
                "DEADLINE_EXCEEDED",
                "UNAVAILABLE",
            ):
                return True
    except Exception:
        pass

    # litellm provider errors.
    try:
        from litellm import exceptions as lite_exc  # type: ignore
        retryable_lite = tuple(
            c for c in (
                getattr(lite_exc, "APIError", None),
                getattr(lite_exc, "APIConnectionError", None),
                getattr(lite_exc, "Timeout", None),
                getattr(lite_exc, "RateLimitError", None),
                getattr(lite_exc, "ServiceUnavailableError", None),
                getattr(lite_exc, "InternalServerError", None),
                getattr(lite_exc, "ContextWindowExceededError", None),
            ) if c is not None
        )
        if retryable_lite and isinstance(exc, retryable_lite):
            return True
    except Exception:
        pass

    return False


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
        model_chain_provider: Callable[[str], list[Any]] | None = None,
        guardrail_service: object | None = None,
        guardrail_profile: str | None = None,
        agent_runs_repo: Any = None,
    ) -> None:
        self._agent = agent
        self._app_name = app_name
        self._session_service = session_service
        self._memory_service = memory_service
        self._board_service = board_service
        self._session_store = session_store
        self._usage_recorder = usage_recorder
        self._guardrail_service = guardrail_service
        self._guardrail_profile = guardrail_profile
        # Optional Firestore repo for per-turn per-author transcript
        # capture. When wired, the runner emits one redacted "user"
        # input message + one "agent" output message per distinct
        # author in the ADK event stream after each turn. UI reads
        # via onSnapshot on agent_runs/{run}/turns/{trace}/messages.
        self._agent_runs_repo = agent_runs_repo
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
        self._model_chain_provider = model_chain_provider
        self._runner = Runner(
            agent=agent,
            app_name=app_name,
            session_service=session_service,
        )

    def _build_fallback_runner(self, next_model: Any) -> Runner:
        """Shallow-clone the agent with a swapped ``model`` and wrap it in
        a fresh ADK Runner. Shares ``app_name`` and ``session_service``
        only; transient runner state is not reused.
        """
        fallback_agent = copy(self._agent)
        fallback_agent.model = next_model
        return Runner(
            agent=fallback_agent,
            app_name=self._app_name,
            session_service=self._session_service,
        )

    async def run(
        self,
        user_id: str,
        session_id: str,
        message: str,
        agent_name: str | None = None,
    ) -> AgentResponse:
        """Execute a single user turn with memory hooks."""
        # Resolve the effective agent name once — used by the observability
        # span, the usage recorder, and the fallback-chain lookup below.
        if agent_name is None:
            agent_name = getattr(self._agent, "name", "agent") or "agent"

        # Root AGENT span for the turn. OpenInference-spec attributes are
        # stamped upfront; LLM token/model attrs are added at turn end
        # (success OR fallback-exhausted failure) so every recorded turn
        # carries a usable summary. When OBSERVABILITY_ENABLED=false the
        # tracer's NoOpSpan makes this effectively free.
        with _tracer.start_as_current_span(f"agent.{agent_name}") as turn_span:
            set_turn_attrs(
                turn_span,
                agent_name=agent_name,
                session_id=session_id,
                user_id=user_id,
            )
            return await self._run_turn(
                user_id=user_id,
                session_id=session_id,
                message=message,
                agent_name=agent_name,
                turn_span=turn_span,
            )

    async def _run_turn(
        self,
        *,
        user_id: str,
        session_id: str,
        message: str,
        agent_name: str,
        turn_span: Any,
    ) -> AgentResponse:
        if self._board_service is not None:
            self._board_service.set_active_user(user_id)
            # session_id is the run_id from the observability layer's POV
            # (SESSION_ID attribute keys the RunRegistry channel).
            self._board_service.set_active_session(session_id)
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

        # Resolve fallback chain. We only need the fallbacks (index>=1);
        # the primary is whatever the existing self._runner is already
        # wrapping — we don't rebuild it on the happy path.
        fallback_models: list[Any] = []
        if self._model_chain_provider is not None:
            try:
                chain = self._model_chain_provider(agent_name) or []
                # Skip index 0 (primary — already in self._runner).
                fallback_models = list(chain[1:])
            except Exception:
                logger.warning(
                    "model_chain_provider(%s) failed; no fallbacks available",
                    agent_name,
                    exc_info=True,
                )
                fallback_models = []

        attempt_index = 0
        active_runner = self._runner
        last_error: BaseException | None = None

        while True:
            response = AgentResponse()
            attempt_start = time.perf_counter()
            tokens_in_total = 0
            tokens_out_total = 0
            model_seen: str | None = None
            # Per-agent bucket so sub-agent work gets its own usage
            # records. Each ADK event has an ``author`` field naming
            # the agent that produced it (orchestrator, research_mgr,
            # research-mgr — ADK normalises name-safe form).
            # Without this split, the recorder attributed every sub-
            # agent LLM call to the root agent, leaving the /admin/usage
            # page showing only the orchestrator regardless of which
            # manager actually did the work.
            per_author: dict[str, dict[str, Any]] = {}

            root_norm = agent_name.replace("_", "-")
            # Per-author transcript capture (text + tool_calls), keyed by
            # the same normalized author name as `per_author`. Written
            # to agent_runs/{run}/turns/{trace}/messages after the turn
            # for the live cockpit + task-details modal.
            per_author_msgs: dict[str, dict[str, Any]] = {}

            def _bucket(author: Any) -> dict[str, Any]:
                # ADK events expose `author` as the agent name string.
                # Defensively coerce anything that isn't a non-empty
                # string back to the root agent so the recorder doesn't
                # choke on pydantic validation.
                name = author if isinstance(author, str) and author else agent_name
                name = name.replace("_", "-")
                return per_author.setdefault(
                    name,
                    {"tokens_in": 0, "tokens_out": 0, "model": None},
                )

            def _msg_bucket(author: Any) -> dict[str, Any]:
                name = author if isinstance(author, str) and author else agent_name
                name = name.replace("_", "-")
                return per_author_msgs.setdefault(
                    name,
                    {"text": "", "tool_calls": []},
                )

            try:
                async for event in active_runner.run_async(
                    user_id=user_id,
                    session_id=session_id,
                    new_message=content,
                ):
                    ev_author = getattr(event, "author", None)
                    if event.content and event.content.parts:
                        for part in event.content.parts:
                            if part.text:
                                response.text += part.text
                                _msg_bucket(ev_author)["text"] += part.text
                            if part.function_call:
                                fc = {
                                    "name": part.function_call.name,
                                    "args": dict(
                                        part.function_call.args or {}
                                    ),
                                    "author": ev_author,
                                }
                                response.tool_calls.append(fc)
                                _msg_bucket(ev_author)["tool_calls"].append({
                                    "name": fc["name"],
                                    "args": fc["args"],
                                })
                    um = getattr(event, "usage_metadata", None)
                    author = getattr(event, "author", None)
                    if um is not None:
                        t_in = getattr(um, "prompt_token_count", 0) or 0
                        t_out = getattr(um, "candidates_token_count", 0) or 0
                        tokens_in_total += t_in
                        tokens_out_total += t_out
                        b = _bucket(author)
                        b["tokens_in"] += t_in
                        b["tokens_out"] += t_out
                    mv = getattr(event, "model_version", None)
                    if mv:
                        if model_seen is None:
                            model_seen = mv
                        b = _bucket(author)
                        if b["model"] is None:
                            b["model"] = mv
                    if event.is_final_response():
                        response.is_final = True
            except Exception as e:  # noqa: BLE001
                run_error = f"{type(e).__name__}: {e}"
                retryable = _is_retryable_model_error(e)
                has_next = retryable and attempt_index < len(fallback_models)
                self._record_turn(
                    user_id=user_id,
                    session_id=session_id,
                    start=attempt_start,
                    success=False,
                    error=run_error,
                    tokens_in=tokens_in_total,
                    tokens_out=tokens_out_total,
                    model_seen=model_seen,
                    tool_calls=response.tool_calls,
                    fallback_index=attempt_index,
                    per_author=per_author,
                )
                if not has_next:
                    # Stamp aggregate LLM attributes on the span before we
                    # re-raise so the trace shows what the failing turn
                    # actually consumed, then record the exception.
                    set_llm_attrs(
                        turn_span,
                        model_name=model_seen,
                        tokens_in=tokens_in_total,
                        tokens_out=tokens_out_total,
                    )
                    try:
                        turn_span.record_exception(e)
                        from opentelemetry.trace import Status, StatusCode
                        turn_span.set_status(
                            Status(StatusCode.ERROR, run_error)
                        )
                    except Exception:
                        pass
                    last_error = e
                    raise
                next_model = fallback_models[attempt_index]
                logger.info(
                    "agent=%s attempt_index=%d failed with %s — retrying "
                    "with fallback index=%d (%r)",
                    agent_name,
                    attempt_index,
                    type(e).__name__,
                    attempt_index + 1,
                    getattr(next_model, "model", next_model),
                )
                attempt_index += 1
                active_runner = self._build_fallback_runner(next_model)
                continue

            # Success.
            self._record_turn(
                user_id=user_id,
                session_id=session_id,
                start=attempt_start,
                success=True,
                error=None,
                tokens_in=tokens_in_total,
                tokens_out=tokens_out_total,
                model_seen=model_seen,
                tool_calls=response.tool_calls,
                fallback_index=attempt_index,
                per_author=per_author,
            )
            self._emit_turn_messages(
                user_id=user_id,
                session_id=session_id,
                turn_span=turn_span,
                user_message=message,
                per_author_msgs=per_author_msgs,
                root_norm=root_norm,
            )
            set_llm_attrs(
                turn_span,
                model_name=model_seen,
                tokens_in=tokens_in_total,
                tokens_out=tokens_out_total,
            )
            if attempt_index and turn_span is not None:
                try:
                    turn_span.set_attribute(
                        "agent.fallback_index", attempt_index
                    )
                except Exception:
                    pass
            # Inline guardrail check — only runs when a service is
            # wired AND enabled. Fail-open on service errors (logged
            # via the service itself). A BLOCK outcome raises and the
            # chat endpoint translates that to a 4xx for the client.
            if self._guardrail_service is not None and getattr(
                self._guardrail_service, "enabled", False
            ) and response.text:
                await self._apply_guardrail(turn_span, response.text)
            break

        _ = last_error  # silence unused-assignment warning

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

    async def _apply_guardrail(self, turn_span: Any, text: str) -> None:
        """Run the configured guardrail service and stamp span attrs."""
        try:
            import json as _json

            result = await self._guardrail_service.check_output(
                text, profile=self._guardrail_profile
            )
        except Exception:
            logger.warning(
                "guardrail: check_output raised (swallowed)", exc_info=True
            )
            return

        try:
            turn_span.set_attribute(
                "guardrail.outcome", result.outcome.value
            )
            if result.violations:
                turn_span.set_attribute(
                    "guardrail.violations",
                    _json.dumps(result.violations_as_json())[:4096],
                )
            if result.duration_ms:
                turn_span.set_attribute(
                    "guardrail.duration_ms", int(result.duration_ms)
                )
        except Exception:
            pass

        outcome_name = getattr(result.outcome, "value", str(result.outcome))
        if outcome_name == "block":
            from gclaw.guardrails.models import GuardrailBlockedError

            raise GuardrailBlockedError(result)

    def _emit_turn_messages(
        self,
        *,
        user_id: str,
        session_id: str,
        turn_span: Any,
        user_message: str,
        per_author_msgs: dict[str, dict[str, Any]],
        root_norm: str,
    ) -> None:
        """Write the user message + each author's output for this turn.

        Redaction happens here (regex-based, from
        ``observability.redaction.redact``) so plaintext prompts +
        responses never hit Firestore. Writes are keyed by the OTel
        trace_id so the turn-doc written by LiveSpanProcessor and this
        messages sub-collection both live under the same trace id.

        Fail-soft: any capture/write failure is logged and swallowed.
        A broken transcript must never break the turn.
        """
        repo = self._agent_runs_repo
        if repo is None:
            return
        try:
            from gclaw.observability.redaction import redact
        except Exception:
            return

        # Pull the trace_id off the turn span. Under the NoOp tracer
        # this returns 0; skip the write in that case.
        try:
            ctx = turn_span.get_span_context()
            trace_id_int = getattr(ctx, "trace_id", 0)
            if not trace_id_int:
                return
            trace_id = format(trace_id_int, "032x")
        except Exception:
            return

        messages: list[dict[str, Any]] = []
        # The user turn itself — single input message, authored "user".
        if user_message:
            messages.append({
                "author": "user",
                "role": "input",
                "text": redact(user_message),
            })

        # One "agent" output per distinct author in the ADK stream.
        # Sort by root first, then alphabetically so the root agent
        # (usually orchestrator) lands directly after the user input.
        def _sort_key(name: str) -> tuple[int, str]:
            return (0 if name == root_norm else 1, name)

        for author in sorted(per_author_msgs.keys(), key=_sort_key):
            bucket = per_author_msgs[author]
            text = bucket.get("text") or ""
            tool_calls = bucket.get("tool_calls") or []
            if not text and not tool_calls:
                continue
            messages.append({
                "author": author,
                "role": "output",
                "text": redact(text) if text else "",
                "tool_calls": [
                    {
                        "name": tc.get("name") or "",
                        # Redact args in case they carry PII (workspace
                        # subjects, research queries, etc.).
                        "args": {
                            k: redact(str(v)) if isinstance(v, str) else v
                            for k, v in (tc.get("args") or {}).items()
                        },
                    }
                    for tc in tool_calls
                ],
            })

        if not messages:
            return
        try:
            repo.append_messages(
                user_id=user_id,
                run_id=session_id,
                trace_id=trace_id,
                messages=messages,
            )
        except Exception:
            logger.warning(
                "turn-messages emit failed for user=%s run=%s",
                user_id,
                session_id,
                exc_info=True,
            )

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
        fallback_index: int = 0,
        per_author: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """Best-effort telemetry emission. Never raises.

        When ``per_author`` is supplied, emit a separate model-call record
        per author (orchestrator, research-mgr, dev-mgr, ...) so the
        /admin/usage page shows which sub-agent actually did what. Without
        this split, every model call and tool call gets filed against the
        root agent and it looks like only the orchestrator is active.
        """
        recorder = self._usage_recorder
        if recorder is None or not getattr(recorder, "enabled", False):
            return
        duration_ms = int((time.perf_counter() - start) * 1000)
        root_name = getattr(self._agent, "name", "agent") or "agent"
        root_norm = root_name.replace("_", "-")
        agent_meta: dict = {"tool_call_count": len(tool_calls)}
        if fallback_index:
            agent_meta["fallback_index"] = fallback_index
        try:
            recorder.record_agent_invoke(
                agent_name=root_name,
                caller=None,
                duration_ms=duration_ms,
                success=success,
                error=error,
                user_id=user_id,
                session_id=session_id,
                metadata=agent_meta,
            )

            authored = per_author or {}
            has_per_author = any(
                b.get("tokens_in") or b.get("tokens_out") or b.get("model")
                for b in authored.values()
            )

            if has_per_author:
                # Emit one model-call record per author. Each sub-agent
                # (research-mgr, dev-mgr, ...) shows up as its own
                # caller on /admin/usage instead of being rolled into
                # the orchestrator row.
                for author_name, bucket in authored.items():
                    t_in = bucket.get("tokens_in") or 0
                    t_out = bucket.get("tokens_out") or 0
                    m_seen = bucket.get("model")
                    if not (t_in or t_out or m_seen):
                        continue
                    model_meta: dict = {
                        "token_source": "adk_usage_metadata",
                        "author": author_name,
                    }
                    if fallback_index:
                        model_meta["fallback_index"] = fallback_index
                    # If the author is not the root agent, also record
                    # an agent-invoke so the AGENT filter on the usage
                    # page surfaces sub-agents. Compare against the
                    # normalized root name — bucket keys use dashes.
                    if author_name and author_name != root_norm:
                        try:
                            recorder.record_agent_invoke(
                                agent_name=author_name,
                                caller=root_name,
                                duration_ms=duration_ms,
                                success=success,
                                error=error,
                                user_id=user_id,
                                session_id=session_id,
                                metadata={"author_of": root_name},
                            )
                        except Exception:
                            logger.warning(
                                "usage: sub-agent invoke record failed",
                                exc_info=True,
                            )
                    recorder.record_model_call(
                        model_id=m_seen or "unknown",
                        provider_id=None,
                        tokens_in=t_in or None,
                        tokens_out=t_out or None,
                        cost_usd=None,
                        duration_ms=duration_ms,
                        success=success,
                        error=error,
                        user_id=user_id,
                        session_id=session_id,
                        caller=author_name or root_name,
                        metadata=model_meta,
                    )
            elif tokens_in or tokens_out or model_seen:
                # Fallback for callers that didn't pass per_author (or
                # for turns where the event stream carried no author).
                model_meta = {
                    "token_source": "adk_usage_metadata",
                }
                if fallback_index:
                    model_meta["fallback_index"] = fallback_index
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
                    caller=root_name,
                    metadata=model_meta,
                )

            for call in tool_calls:
                raw_author = call.get("author")
                caller = (
                    raw_author.replace("_", "-")
                    if isinstance(raw_author, str) and raw_author
                    else root_name
                )
                recorder.record_tool_call(
                    tool_name=call.get("name") or "unknown",
                    agent_name=caller,
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
