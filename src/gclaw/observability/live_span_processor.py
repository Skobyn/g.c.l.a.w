"""OTel ``SpanProcessor`` that powers the live agent dashboard.

For every AGENT-kind span that ends, it:

1. Pushes a ``{'event': 'span.end', 'data': ...}`` dict into the per-run
   asyncio queue — the SSE endpoint in
   :mod:`gclaw.api.dashboard_routes` drains it for the live trace feed.
2. Merge-upserts a summary doc at
   ``/users/{user_id}/agent_runs/{run_id}`` in Firestore — the Next.js
   PWA reads it via ``onSnapshot`` for the NowPlaying card + context
   gauge.
3. Throttles Firestore writes to ~1/sec per run (Firestore soft limit).

Registered alongside the Cloud Trace + OTLP exporters, but doesn't
forward spans anywhere OTel-y — strictly a fan-out to our own
surfaces. Non-AGENT spans are ignored (LLM/TOOL spans auto-emitted by
the OpenInference instrumentors bloat the dashboard feed).

Fail-soft: every path swallows exceptions so a dashboard bug never
breaks span emission.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor

from gclaw.observability.constants import (
    GRAPH_NODE_ID,
    LLM_MODEL_NAME,
    LLM_PROVIDER,
    LLM_TOKEN_COMPLETION,
    LLM_TOKEN_PROMPT,
    LLM_TOKEN_TOTAL,
    SESSION_ID,
    USER_ID,
)
from gclaw.observability.run_registry import RunRegistry

logger = logging.getLogger(__name__)

_SPAN_KIND_KEY = "openinference.span.kind"
_AGENT_KIND = "AGENT"


class LiveSpanProcessor(SpanProcessor):
    """Fans AGENT spans to RunRegistry + Firestore for the live dashboard."""

    def __init__(
        self,
        *,
        run_registry: RunRegistry,
        firestore_repo: Any | None = None,
        throttle_seconds: float = 1.0,
    ) -> None:
        self._registry = run_registry
        self._repo = firestore_repo
        self._throttle = throttle_seconds
        self._last_firestore_write: dict[str, float] = {}

    def set_firestore_repo(self, repo: Any) -> None:
        """Inject the Firestore repo post-construction.

        Used by ``build_app()`` because the TracerProvider is registered
        before Firestore is constructed.
        """
        self._repo = repo

    # ── SpanProcessor protocol ────────────────────────────────────────

    def on_start(
        self, span: Any, parent_context: Any | None = None
    ) -> None:  # noqa: D401
        return None

    def on_end(self, span: ReadableSpan) -> None:
        try:
            attrs = dict(span.attributes or {})
            if attrs.get(_SPAN_KIND_KEY) != _AGENT_KIND:
                return
            run_id = str(attrs.get(SESSION_ID) or "")
            user_id = str(attrs.get(USER_ID) or "")
            if not run_id:
                return

            event = _build_event(span, attrs)
            self._registry.put_nowait(run_id, event)

            if self._repo is not None and user_id:
                now = time.monotonic()
                last = self._last_firestore_write.get(run_id, 0.0)
                if (now - last) >= self._throttle:
                    self._last_firestore_write[run_id] = now
                    try:
                        self._repo.upsert(
                            user_id=user_id, run_id=run_id, event=event
                        )
                    except Exception:
                        logger.warning(
                            "LiveSpanProcessor: Firestore upsert failed",
                            exc_info=True,
                        )
        except Exception:
            logger.warning(
                "LiveSpanProcessor.on_end failed (swallowed)", exc_info=True
            )

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


def _build_event(span: ReadableSpan, attrs: dict[str, Any]) -> dict[str, Any]:
    tokens_in = attrs.get(LLM_TOKEN_PROMPT)
    tokens_out = attrs.get(LLM_TOKEN_COMPLETION)
    tokens_total = attrs.get(LLM_TOKEN_TOTAL)
    status_obj = getattr(span, "status", None)
    status_code = getattr(
        getattr(status_obj, "status_code", None), "name", "UNSET"
    )
    return {
        "event": "span.end",
        "data": {
            "span_id": _hex_span_id(span),
            "trace_id": _hex_trace_id(span),
            "name": span.name,
            "agent": attrs.get(GRAPH_NODE_ID),
            "model_id": attrs.get(LLM_MODEL_NAME),
            "provider": attrs.get(LLM_PROVIDER),
            "tokens": {
                "in": tokens_in,
                "out": tokens_out,
                "total": tokens_total,
            },
            "status": status_code,
            "started_at": span.start_time,
            "ended_at": span.end_time,
        },
    }


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
