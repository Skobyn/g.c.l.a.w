"""OpenTelemetry tracer provider bootstrap.

No-op when ``settings.observability_enabled`` is false. When enabled:
  * Registers a ``TracerProvider`` with a ``Resource`` carrying the
    service name/version.
  * Adds a Cloud Trace ``BatchSpanProcessor`` (primary sink).
  * Adds an OTLP/HTTP ``BatchSpanProcessor`` when
    ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set (Phoenix, in Phase 3).
  * Registers OpenInference instrumentors for ADK + LiteLLM.

Fail-soft: any exporter or instrumentor that fails to initialize logs a
warning and is skipped. The app must never fail to boot because of
observability.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def init_tracing(
    settings: Any,
    *,
    extra_processors: list[Any] | None = None,
) -> Optional[Any]:
    """Initialize the global OpenTelemetry tracer provider.

    Returns the ``TracerProvider`` on success, ``None`` when disabled or
    when the OTel SDK is unavailable. Idempotent — a second call returns
    the existing provider and adds any new ``extra_processors`` to it.

    ``extra_processors`` are registered AFTER the Cloud Trace + OTLP
    exporters so live-fanout processors (e.g. LiveSpanProcessor) run
    alongside the durable sinks, not instead of them.
    """
    if not getattr(settings, "observability_enabled", False):
        return None

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
    except ImportError:
        logger.warning("tracing: OTel SDK not installed; tracing disabled")
        return None

    existing = trace.get_tracer_provider()
    if isinstance(existing, TracerProvider):
        for proc in extra_processors or []:
            try:
                existing.add_span_processor(proc)
            except Exception:
                logger.warning(
                    "tracing: failed to add extra processor", exc_info=True
                )
        return existing

    resource = Resource.create(
        {
            "service.name": getattr(
                settings, "otel_service_name", "gclaw-backend"
            ),
            "service.version": _pkg_version(),
        }
    )
    sampler = TraceIdRatioBased(
        getattr(settings, "otel_sampling_ratio", 1.0)
    )
    provider = TracerProvider(resource=resource, sampler=sampler)

    _register_cloud_trace_exporter(provider, settings)
    _register_otlp_exporter(provider, settings)

    for proc in extra_processors or []:
        try:
            provider.add_span_processor(proc)
        except Exception:
            logger.warning(
                "tracing: failed to add extra processor", exc_info=True
            )

    trace.set_tracer_provider(provider)

    _register_instrumentors()

    logger.info(
        "tracing: initialized (service=%s, sampling=%s, extra_processors=%d)",
        getattr(settings, "otel_service_name", "gclaw-backend"),
        getattr(settings, "otel_sampling_ratio", 1.0),
        len(extra_processors or []),
    )
    return provider


def _register_cloud_trace_exporter(provider: Any, settings: Any) -> None:
    project_id = getattr(settings, "gcp_project_id", None)
    if not project_id:
        logger.warning(
            "tracing: gcp_project_id empty; skipping Cloud Trace exporter"
        )
        return
    try:
        from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider.add_span_processor(
            BatchSpanProcessor(
                CloudTraceSpanExporter(project_id=project_id),
                schedule_delay_millis=1000,
                max_queue_size=2048,
            )
        )
        logger.info(
            "tracing: Cloud Trace exporter registered (project=%s)",
            project_id,
        )
    except Exception:
        logger.warning(
            "tracing: Cloud Trace exporter init failed", exc_info=True
        )


def _register_otlp_exporter(provider: Any, settings: Any) -> None:
    endpoint = getattr(settings, "otel_exporter_otlp_endpoint", "")
    if not endpoint:
        return
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        headers = _parse_otlp_headers(
            getattr(settings, "otel_exporter_otlp_headers", "")
        )
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=endpoint, headers=headers),
                schedule_delay_millis=1000,
                max_queue_size=2048,
            )
        )
        logger.info(
            "tracing: OTLP exporter registered (endpoint=%s)", endpoint
        )
    except Exception:
        logger.warning(
            "tracing: OTLP exporter init failed", exc_info=True
        )


def _register_instrumentors() -> None:
    try:
        from openinference.instrumentation.google_adk import (
            GoogleADKInstrumentor,
        )

        GoogleADKInstrumentor().instrument()
        logger.info("tracing: GoogleADKInstrumentor registered")
    except Exception:
        logger.warning(
            "tracing: GoogleADKInstrumentor unavailable", exc_info=True
        )

    try:
        from openinference.instrumentation.litellm import LiteLLMInstrumentor

        LiteLLMInstrumentor().instrument()
        logger.info("tracing: LiteLLMInstrumentor registered")
    except Exception:
        logger.warning(
            "tracing: LiteLLMInstrumentor unavailable", exc_info=True
        )


def _pkg_version() -> str:
    try:
        from importlib.metadata import version

        return version("gclaw")
    except Exception:
        return "unknown"


def _parse_otlp_headers(raw: Optional[str]) -> Optional[dict]:
    if not raw:
        return None
    headers: dict[str, str] = {}
    for pair in raw.split(","):
        if "=" in pair:
            k, v = pair.split("=", 1)
            headers[k.strip()] = v.strip()
    return headers or None
