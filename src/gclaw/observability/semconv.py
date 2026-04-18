"""OpenInference semantic-convention helpers for span attribute population.

The runner (and later, the live span processor) stamp the same bundles
of attributes on spans; centralizing the mapping keeps call sites
readable and makes schema changes a single-file edit.

All helpers are safe to call with a ``None`` span or a non-recording
NoOp span — they silently skip rather than raising.
"""

from __future__ import annotations

from typing import Any

from gclaw.observability.constants import (
    GRAPH_NODE_ID,
    GRAPH_NODE_PARENT_ID,
    LLM_MODEL_NAME,
    LLM_PROVIDER,
    LLM_TOKEN_CACHE_READ,
    LLM_TOKEN_COMPLETION,
    LLM_TOKEN_PROMPT,
    LLM_TOKEN_TOTAL,
    SESSION_ID,
    TOOL_CALL_ID,
    TOOL_NAME,
    TOOL_PARAMETERS,
    USER_ID,
)

# OpenInference namespaces the span-kind attribute on the span itself.
SPAN_KIND_KEY = "openinference.span.kind"
SPAN_KIND_AGENT = "AGENT"
SPAN_KIND_LLM = "LLM"
SPAN_KIND_TOOL = "TOOL"

# Tool parameter payloads are truncated to 4 KiB — Cloud Trace rejects
# per-attribute values larger than 8 KiB and oversized tool.args are a
# common cause of dropped spans.
_TOOL_PARAM_MAX_BYTES = 4096


def set_turn_attrs(
    span: Any,
    *,
    agent_name: str,
    session_id: str,
    user_id: str,
    parent_agent: str = "",
) -> None:
    """Stamp AGENT-kind identity attributes on a root turn span."""
    if not _is_recording(span):
        return
    try:
        span.set_attribute(SPAN_KIND_KEY, SPAN_KIND_AGENT)
        span.set_attribute(GRAPH_NODE_ID, agent_name)
        if parent_agent:
            span.set_attribute(GRAPH_NODE_PARENT_ID, parent_agent)
        if session_id:
            span.set_attribute(SESSION_ID, session_id)
        if user_id:
            span.set_attribute(USER_ID, user_id)
    except Exception:
        pass


def set_llm_attrs(
    span: Any,
    *,
    model_name: str | None = None,
    provider: str | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    tokens_cache_read: int | None = None,
) -> None:
    """Stamp LLM usage attributes on a span. Missing values are skipped."""
    if not _is_recording(span):
        return
    try:
        if model_name:
            span.set_attribute(LLM_MODEL_NAME, model_name)
        if provider:
            span.set_attribute(LLM_PROVIDER, provider)
        if tokens_in is not None:
            span.set_attribute(LLM_TOKEN_PROMPT, int(tokens_in))
        if tokens_out is not None:
            span.set_attribute(LLM_TOKEN_COMPLETION, int(tokens_out))
        if tokens_in is not None or tokens_out is not None:
            span.set_attribute(
                LLM_TOKEN_TOTAL, int((tokens_in or 0) + (tokens_out or 0))
            )
        if tokens_cache_read is not None:
            span.set_attribute(LLM_TOKEN_CACHE_READ, int(tokens_cache_read))
    except Exception:
        pass


def set_tool_attrs(
    span: Any,
    *,
    name: str,
    parameters_json: str | None = None,
    call_id: str | None = None,
) -> None:
    """Stamp TOOL-kind attributes. ``parameters_json`` is truncated to 4 KiB."""
    if not _is_recording(span):
        return
    try:
        span.set_attribute(SPAN_KIND_KEY, SPAN_KIND_TOOL)
        span.set_attribute(TOOL_NAME, name)
        if parameters_json is not None:
            span.set_attribute(
                TOOL_PARAMETERS, parameters_json[:_TOOL_PARAM_MAX_BYTES]
            )
        if call_id:
            span.set_attribute(TOOL_CALL_ID, call_id)
    except Exception:
        pass


def _is_recording(span: Any) -> bool:
    """True when the span will actually retain attributes (not NoOp, not None)."""
    if span is None:
        return False
    try:
        return bool(span.is_recording())
    except Exception:
        return False
