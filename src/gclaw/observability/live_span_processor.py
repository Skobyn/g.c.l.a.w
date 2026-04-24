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
        cost_lookup: Any | None = None,
    ) -> None:
        self._registry = run_registry
        self._repo = firestore_repo
        self._throttle = throttle_seconds
        self._last_firestore_write: dict[str, float] = {}
        self._cost_lookup = cost_lookup

    def set_firestore_repo(self, repo: Any) -> None:
        """Inject the Firestore repo post-construction.

        Used by ``build_app()`` because the TracerProvider is registered
        before Firestore is constructed.
        """
        self._repo = repo

    def set_cost_lookup(self, cost_lookup: Any) -> None:
        """Inject cost_lookup post-construction so per-turn / per-session
        cost fields land on the live dashboard docs."""
        self._cost_lookup = cost_lookup

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

            event = _build_event(span, attrs, cost_lookup=self._cost_lookup)
            self._registry.put_nowait(run_id, event)

            if self._repo is not None and user_id:
                # Throttle Firestore writes per-run, but ALWAYS allow
                # writes that carry meaningful data (tokens or model)
                # to land — otherwise the sub-spans that fire during a
                # turn (AgentTool invocations from ADK's OpenInference
                # instrumentor, all carrying SPAN_KIND=AGENT but no
                # tokens) can eat the throttle budget, and the root
                # turn span's end-of-turn write — the one with the
                # actual tokens and model — gets silently dropped.
                data = event.get("data") or {}
                tokens = data.get("tokens") or {}
                # Only count input / output tokens — `total` is derived
                # by the instrumentor and can be set even when the real
                # token fields are null (it emits 0 in that case).
                has_meaningful = (
                    data.get("model_id")
                    or data.get("cost_usd") is not None
                    or tokens.get("in") is not None
                    or tokens.get("out") is not None
                )
                now = time.monotonic()
                last = self._last_firestore_write.get(run_id, 0.0)
                if has_meaningful or (now - last) >= self._throttle:
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


def _build_event(
    span: ReadableSpan,
    attrs: dict[str, Any],
    *,
    cost_lookup: Any | None = None,
) -> dict[str, Any]:
    tokens_in = attrs.get(LLM_TOKEN_PROMPT)
    tokens_out = attrs.get(LLM_TOKEN_COMPLETION)
    tokens_total = attrs.get(LLM_TOKEN_TOTAL)
    model_id = attrs.get(LLM_MODEL_NAME)
    status_obj = getattr(span, "status", None)
    status_code = getattr(
        getattr(status_obj, "status_code", None), "name", "UNSET"
    )
    # Compute per-span cost if the model catalog knows about the model.
    # Fail-soft — an unknown model or a lookup raise just leaves the
    # field None (the UI renders "—" for that).
    cost_usd: float | None = None
    if (
        cost_lookup is not None
        and model_id
        and tokens_in is not None
        and tokens_out is not None
    ):
        try:
            cost_usd = cost_lookup(model_id, int(tokens_in), int(tokens_out))
        except Exception:
            cost_usd = None
    return {
        "event": "span.end",
        "data": {
            "span_id": _hex_span_id(span),
            "trace_id": _hex_trace_id(span),
            "name": span.name,
            "agent": attrs.get(GRAPH_NODE_ID),
            "model_id": model_id,
            "provider": attrs.get(LLM_PROVIDER),
            "tokens": {
                "in": tokens_in,
                "out": tokens_out,
                "total": tokens_total,
            },
            "cost_usd": cost_usd,
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
