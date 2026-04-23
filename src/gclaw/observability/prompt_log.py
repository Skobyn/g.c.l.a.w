"""GCS-backed prompt-response log (ADR-0004).

Each ``call_llm`` span produces two JSON objects in GCS — one for
the prompt, one for the response — at a hive-partitioned path::

    gs://<bucket>/yyyy=YYYY/mm=MM/dd=DD/hh=HH/<session_id>/<event_id>.{prompt,response}.json

The :class:`PromptLogSpanProcessor` filters spans (LLM kind, name
``call_llm``), extracts the prompt + response text from OpenInference
attributes, applies :func:`gclaw.observability.redaction.redact_object`,
and hands the payloads to :class:`PromptLogWriter` for fire-and-forget
upload. Failures are warning-logged and swallowed — no GCS hiccup
ever blocks the agent path.

The writer pre-computes URIs from ``(event_time, session_id, event_id)``
deterministically so the ADR-0003 BigQuery writer can recover them
later without a shared in-memory map: see :func:`build_prompt_uri` /
:func:`build_response_uri`.
"""

from __future__ import annotations

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor

logger = logging.getLogger(__name__)

# Span name emitted by ADK's BaseLlmFlow.trace_call_llm. The
# OpenInference google_adk instrumentor wraps that function and
# stamps SPAN_KIND=LLM onto the active span; we filter on both so
# spans from other instrumentors (e.g. raw LiteLLM) that happen to
# be LLM-kind also get logged.
_CALL_LLM_SPAN_NAME = "call_llm"
_SPAN_KIND_KEY = "openinference.span.kind"
_LLM_KIND = "LLM"

# Per-call upload deadline. GCS that ack > 2s is treated as a drop;
# the writer logs a warning and moves on. Conservative because the
# log lives behind a fail-open: lost rows are recoverable from
# Phoenix / Cloud Trace, but stalled chats are not.
_UPLOAD_TIMEOUT_SECONDS = 2.0


# ── URI helpers ──────────────────────────────────────────────────────


def _hive_prefix(when: datetime) -> str:
    when = when.astimezone(timezone.utc)
    return (
        f"yyyy={when.year:04d}/"
        f"mm={when.month:02d}/"
        f"dd={when.day:02d}/"
        f"hh={when.hour:02d}"
    )


def build_prompt_uri(
    *, bucket: str, when: datetime, session_id: str, event_id: str
) -> str:
    """Deterministic ``gs://`` URI for the prompt JSON object.

    ADR-0003's BQ writer can reconstruct the same URI from
    ``(event_time, session_id, event_id)`` without a shared map.
    """
    return (
        f"gs://{bucket}/{_hive_prefix(when)}/"
        f"{session_id}/{event_id}.prompt.json"
    )


def build_response_uri(
    *, bucket: str, when: datetime, session_id: str, event_id: str
) -> str:
    """Deterministic ``gs://`` URI for the response JSON object."""
    return (
        f"gs://{bucket}/{_hive_prefix(when)}/"
        f"{session_id}/{event_id}.response.json"
    )


# ── Writer ───────────────────────────────────────────────────────────


class PromptLogWriter:
    """Async, fail-open uploader for prompt/response JSON pairs.

    Construction is cheap — the GCS client is built lazily on first
    upload so test environments without ADC can import the module
    without crashing.
    """

    def __init__(
        self,
        *,
        bucket_name: str,
        project: str | None = None,
        max_workers: int = 4,
        upload_timeout_seconds: float = _UPLOAD_TIMEOUT_SECONDS,
    ) -> None:
        self._bucket_name = bucket_name
        self._project = project
        self._client: Any = None
        self._client_lock = threading.Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="prompt-log",
        )
        self._upload_timeout = upload_timeout_seconds

    @property
    def bucket_name(self) -> str:
        return self._bucket_name

    def _get_bucket(self) -> Any:
        # Build the client + bucket handle once and cache. Lazy so the
        # writer is constructible in tests without GCS creds.
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    from google.cloud import storage

                    self._client = storage.Client(project=self._project)
        return self._client.bucket(self._bucket_name)

    def _upload_blob(self, name: str, payload: bytes) -> None:
        bucket = self._get_bucket()
        blob = bucket.blob(name)
        blob.upload_from_string(payload, content_type="application/json")

    def upload_pair(
        self,
        *,
        when: datetime,
        session_id: str,
        event_id: str,
        prompt: dict[str, Any],
        response: dict[str, Any],
    ) -> tuple[str, str]:
        """Schedule prompt + response uploads. Returns the two URIs.

        Fire-and-forget: scheduling happens synchronously, the actual
        upload runs on a worker thread. Errors are caught + logged; the
        URIs are returned regardless so the BQ writer can still record
        the (eventually consistent) blob path.
        """
        prompt_uri = build_prompt_uri(
            bucket=self._bucket_name,
            when=when,
            session_id=session_id,
            event_id=event_id,
        )
        response_uri = build_response_uri(
            bucket=self._bucket_name,
            when=when,
            session_id=session_id,
            event_id=event_id,
        )
        prompt_name = prompt_uri.removeprefix(f"gs://{self._bucket_name}/")
        response_name = response_uri.removeprefix(
            f"gs://{self._bucket_name}/"
        )
        prompt_payload = json.dumps(
            prompt, ensure_ascii=False, default=str
        ).encode("utf-8")
        response_payload = json.dumps(
            response, ensure_ascii=False, default=str
        ).encode("utf-8")

        self._submit(prompt_name, prompt_payload, prompt_uri)
        self._submit(response_name, response_payload, response_uri)
        return prompt_uri, response_uri

    def _submit(self, name: str, payload: bytes, uri: str) -> None:
        try:
            future = self._executor.submit(
                self._upload_blob, name, payload
            )
        except RuntimeError:
            # Executor already shut down — drop and log.
            logger.warning(
                "prompt-log: executor shut down; dropping upload %s", uri
            )
            return

        def _on_done(fut: Any, _uri: str = uri) -> None:
            try:
                fut.result(timeout=self._upload_timeout)
            except Exception:
                logger.warning(
                    "prompt-log: upload failed for %s (swallowed)",
                    _uri,
                    exc_info=True,
                )

        future.add_done_callback(_on_done)

    def shutdown(self) -> None:
        """Drain the worker pool. Used on tracer-provider shutdown."""
        self._executor.shutdown(wait=False, cancel_futures=False)


# ── Span processor ───────────────────────────────────────────────────


class PromptLogSpanProcessor(SpanProcessor):
    """Reads ``call_llm`` spans and dispatches their prompt/response
    payloads to :class:`PromptLogWriter`.

    Fail-soft on every path: a malformed span attribute, a missing
    bucket, or a transient GCS error never raises out of
    :meth:`on_end`.
    """

    def __init__(self, *, writer: PromptLogWriter) -> None:
        self._writer = writer

    def on_start(
        self, span: Any, parent_context: Any | None = None
    ) -> None:  # noqa: D401
        return None

    def on_end(self, span: ReadableSpan) -> None:
        try:
            attrs = dict(span.attributes or {})
            if not _is_call_llm_span(span, attrs):
                return

            event_id = _hex_span_id(span)
            trace_id = _hex_trace_id(span)
            session_id = (
                str(attrs.get("session.id") or "") or "unknown-session"
            )
            user_id = str(attrs.get("user.id") or "")
            agent_name = str(attrs.get("graph.node.id") or "")
            model = str(attrs.get("llm.model_name") or "")
            provider = str(attrs.get("llm.provider") or "")

            when = _utc_from_span(span)
            prompt_payload = _build_prompt_payload(
                attrs=attrs,
                event_id=event_id,
                trace_id=trace_id,
                session_id=session_id,
                user_id=user_id,
                agent_name=agent_name,
                model=model,
                provider=provider,
                when=when,
            )
            response_payload = _build_response_payload(
                attrs=attrs,
                event_id=event_id,
                trace_id=trace_id,
                span_start=span.start_time,
                span_end=span.end_time,
                when=when,
            )

            # Redaction MUST run before upload.
            from gclaw.observability.redaction import redact_object

            prompt_payload = redact_object(prompt_payload)
            response_payload = redact_object(response_payload)

            self._writer.upload_pair(
                when=when,
                session_id=session_id,
                event_id=event_id,
                prompt=prompt_payload,
                response=response_payload,
            )
        except Exception:
            logger.warning(
                "PromptLogSpanProcessor.on_end failed (swallowed)",
                exc_info=True,
            )

    def shutdown(self) -> None:
        try:
            self._writer.shutdown()
        except Exception:
            logger.warning(
                "prompt-log: writer shutdown failed", exc_info=True
            )

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


# ── Span attribute extraction ────────────────────────────────────────


def _is_call_llm_span(span: ReadableSpan, attrs: dict[str, Any]) -> bool:
    name = getattr(span, "name", "") or ""
    if name == _CALL_LLM_SPAN_NAME:
        return True
    return attrs.get(_SPAN_KIND_KEY) == _LLM_KIND


def _build_prompt_payload(
    *,
    attrs: dict[str, Any],
    event_id: str,
    trace_id: str,
    session_id: str,
    user_id: str,
    agent_name: str,
    model: str,
    provider: str,
    when: datetime,
) -> dict[str, Any]:
    system_prompt, messages = _extract_input_messages(attrs)
    # Fall back to gen_ai.* / input.value if no per-message attrs.
    if not messages:
        raw_input = (
            attrs.get("gen_ai.prompt")
            or attrs.get("input.value")
            or ""
        )
        if raw_input:
            messages = [{"role": "user", "content": str(raw_input)}]
    tools_declared = _extract_tools(attrs)
    return {
        "event_id": event_id,
        "trace_id": trace_id,
        "session_id": session_id,
        "user_id": user_id,
        "agent_name": agent_name,
        "model": model,
        "provider": provider,
        "system_prompt": system_prompt,
        "messages": messages,
        "tools_declared": tools_declared,
        "request_at": when.isoformat(),
    }


def _build_response_payload(
    *,
    attrs: dict[str, Any],
    event_id: str,
    trace_id: str,
    span_start: int | None,
    span_end: int | None,
    when: datetime,
) -> dict[str, Any]:
    response_text = _extract_output_text(attrs)
    if not response_text:
        response_text = str(
            attrs.get("gen_ai.completion")
            or attrs.get("output.value")
            or ""
        )
    latency_ms: int | None = None
    if span_start is not None and span_end is not None:
        # OTel span times are nanoseconds since epoch.
        latency_ms = max(0, int((span_end - span_start) // 1_000_000))
    return {
        "event_id": event_id,
        "trace_id": trace_id,
        "response_text": response_text,
        "tool_calls": _extract_tool_calls(attrs),
        "stop_reason": str(attrs.get("llm.response.stop_reason") or ""),
        "input_tokens": _safe_int(attrs.get("llm.token_count.prompt")),
        "output_tokens": _safe_int(
            attrs.get("llm.token_count.completion")
        ),
        "latency_ms": latency_ms,
        "response_at": when.isoformat(),
    }


def _extract_input_messages(
    attrs: dict[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    """Return ``(system_prompt, messages)`` from ``llm.input_messages.*``.

    OpenInference flattens messages onto the span as
    ``llm.input_messages.<i>.message.role`` /
    ``llm.input_messages.<i>.message.content``. We fold them back into
    a list, lifting the system role out separately so the JSON shape
    matches the ADR-0004 schema.
    """
    by_index: dict[int, dict[str, Any]] = {}
    prefix = "llm.input_messages."
    for key, value in attrs.items():
        if not isinstance(key, str) or not key.startswith(prefix):
            continue
        rest = key[len(prefix):]
        idx_str, _, suffix = rest.partition(".")
        try:
            idx = int(idx_str)
        except ValueError:
            continue
        slot = by_index.setdefault(idx, {})
        if suffix == "message.role":
            slot["role"] = str(value)
        elif suffix == "message.content":
            slot["content"] = str(value)

    system_prompt = ""
    messages: list[dict[str, Any]] = []
    for idx in sorted(by_index):
        msg = by_index[idx]
        if msg.get("role") == "system" and not system_prompt:
            system_prompt = msg.get("content", "")
            continue
        messages.append(
            {
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            }
        )
    return system_prompt, messages


def _extract_output_text(attrs: dict[str, Any]) -> str:
    pieces: list[str] = []
    prefix = "llm.output_messages."
    by_index: dict[int, str] = {}
    for key, value in attrs.items():
        if not isinstance(key, str) or not key.startswith(prefix):
            continue
        rest = key[len(prefix):]
        idx_str, _, suffix = rest.partition(".")
        try:
            idx = int(idx_str)
        except ValueError:
            continue
        if suffix == "message.content":
            by_index[idx] = str(value)
    for idx in sorted(by_index):
        pieces.append(by_index[idx])
    return "\n".join(pieces)


def _extract_tools(attrs: dict[str, Any]) -> list[str]:
    names: list[tuple[int, str]] = []
    prefix = "llm.tools."
    for key, value in attrs.items():
        if not isinstance(key, str) or not key.startswith(prefix):
            continue
        rest = key[len(prefix):]
        idx_str, _, suffix = rest.partition(".")
        try:
            idx = int(idx_str)
        except ValueError:
            continue
        if suffix.endswith("tool.name") or suffix.endswith("name"):
            names.append((idx, str(value)))
    return [n for _, n in sorted(set(names))]


def _extract_tool_calls(attrs: dict[str, Any]) -> list[dict[str, Any]]:
    by_index: dict[int, dict[str, Any]] = {}
    prefix = "llm.output_messages."
    for key, value in attrs.items():
        if not isinstance(key, str) or not key.startswith(prefix):
            continue
        rest = key[len(prefix):]
        # Shape: <i>.message.tool_calls.<j>.tool_call.function.{name,arguments}
        if ".tool_calls." not in rest:
            continue
        try:
            _, after = rest.split(".tool_calls.", 1)
            j_str, _, suffix = after.partition(".")
            j = int(j_str)
        except ValueError:
            continue
        slot = by_index.setdefault(j, {})
        if suffix.endswith("function.name"):
            slot["name"] = str(value)
        elif suffix.endswith("function.arguments"):
            slot["arguments"] = str(value)
    return [by_index[j] for j in sorted(by_index)]


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _hex_span_id(span: ReadableSpan) -> str:
    try:
        return format(span.context.span_id, "016x")
    except Exception:
        return ""


def _hex_trace_id(span: ReadableSpan) -> str:
    try:
        return format(span.context.trace_id, "032x")
    except Exception:
        return ""


def _utc_from_span(span: ReadableSpan) -> datetime:
    end = getattr(span, "end_time", None)
    if isinstance(end, int) and end > 0:
        return datetime.fromtimestamp(end / 1_000_000_000, tz=timezone.utc)
    return datetime.now(tz=timezone.utc)
