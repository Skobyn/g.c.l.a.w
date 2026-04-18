"""Observability package — OpenTelemetry tracing + OpenInference spans.

Public API: :func:`init_tracing` (no-op when OBSERVABILITY_ENABLED=false).
"""

from gclaw.observability.tracing import init_tracing

__all__ = ["init_tracing"]
