"""Observability package — OpenTelemetry tracing + OpenInference spans.

Public API:
  - :func:`init_tracing` — boot the tracer provider (no-op when
    ``OBSERVABILITY_ENABLED=false``).
  - :class:`LiveSpanProcessor` — fans AGENT spans to the live dashboard.
  - :class:`RunRegistry` — per-run asyncio queue registry for SSE.
  - :class:`PromptLogWriter` / :class:`PromptLogSpanProcessor` — writes
    prompt + response JSON to GCS for compliance / replay (ADR-0004).
"""

from gclaw.observability.live_span_processor import LiveSpanProcessor
from gclaw.observability.prompt_log import (
    PromptLogSpanProcessor,
    PromptLogWriter,
)
from gclaw.observability.run_registry import RunRegistry
from gclaw.observability.tracing import init_tracing

__all__ = [
    "init_tracing",
    "LiveSpanProcessor",
    "PromptLogSpanProcessor",
    "PromptLogWriter",
    "RunRegistry",
]
