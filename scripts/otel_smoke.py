"""Manual smoke test for the observability tracer provider.

Usage:
    OBSERVABILITY_ENABLED=true \\
    GCP_PROJECT_ID=<project> \\
    uv run python scripts/otel_smoke.py

Emits one parent + one child span, flushes, prints the trace ID so the
operator can look it up in Cloud Trace. Exits 0 on success, 1 otherwise.
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    if os.environ.get("OBSERVABILITY_ENABLED", "false").lower() != "true":
        print(
            "OBSERVABILITY_ENABLED is not true; set it before running.",
            file=sys.stderr,
        )
        return 1

    from gclaw.observability.tracing import init_tracing
    from gclaw.settings import get_settings

    settings = get_settings()
    provider = init_tracing(settings)
    if provider is None:
        print("init_tracing returned None — tracing is disabled.", file=sys.stderr)
        return 1

    from opentelemetry import trace

    tracer = trace.get_tracer("otel_smoke")
    with tracer.start_as_current_span("otel-smoke-parent") as parent:
        parent.set_attribute("smoke.test", True)
        trace_id = format(parent.get_span_context().trace_id, "032x")
        with tracer.start_as_current_span("otel-smoke-child") as child:
            child.set_attribute("smoke.role", "child")

    try:
        provider.force_flush(timeout_millis=5000)
    finally:
        provider.shutdown()

    print(f"span flushed (trace_id={trace_id})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
