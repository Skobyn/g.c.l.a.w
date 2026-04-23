"""Microbenchmarks for the observability + eval hot paths.

Run:
    uv run python benchmarks/bench_observability.py

Reports per-call wall time + ops/sec for each hot path. Tracks the
budget the ADRs promised:

  * BQ writer enqueue: cheap (in-memory dict shape)
  * BQ processor on_end: <1ms target — runs synchronously on every span
  * Prompt log redaction: <0.5ms target — runs on every prompt + response
  * Prompt log payload build: <2ms target
  * Eval evalset load + dump round-trip: <10ms

These are the path-of-execution operations that show up in chat latency.
The actual GCS / BQ network calls are async + fire-and-forget, so they
don't add to chat latency — they don't need a budget here.
"""

from __future__ import annotations

import json
import statistics
import time
from typing import Callable
from unittest.mock import MagicMock

# Force a deterministic, network-free test environment for any module
# that probes env at import time.
import os
os.environ.setdefault("GCP_PROJECT_ID", "bench-project")
os.environ.setdefault("FIREBASE_AUTH_ENABLED", "false")


def measure(fn: Callable[[], None], n: int = 5000, warmup: int = 100) -> dict:
    for _ in range(warmup):
        fn()
    samples = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - t0)
    samples.sort()
    return {
        "n": n,
        "p50_us": samples[n // 2] * 1e6,
        "p95_us": samples[int(n * 0.95)] * 1e6,
        "p99_us": samples[int(n * 0.99)] * 1e6,
        "max_us": samples[-1] * 1e6,
        "mean_us": statistics.mean(samples) * 1e6,
        "ops_per_sec": 1.0 / statistics.mean(samples),
    }


def report(label: str, result: dict, budget_us: float | None = None) -> None:
    bar = "PASS" if (budget_us is None or result["p99_us"] <= budget_us) else "OVER"
    budget = f" (budget {budget_us:.0f}µs)" if budget_us else ""
    print(
        f"  {label:50s} "
        f"p50={result['p50_us']:>7.1f}µs  "
        f"p95={result['p95_us']:>7.1f}µs  "
        f"p99={result['p99_us']:>7.1f}µs  "
        f"{result['ops_per_sec']:>9,.0f} ops/s  "
        f"[{bar}]{budget}"
    )


# ---------- Redaction (ADR-0004) ----------


def bench_redaction() -> None:
    print("\n## Redaction (ADR-0004) — runs on every prompt + response payload")
    from gclaw.observability.redaction import redact, redact_object

    plain_text = (
        "User asked about the weather in Boston. The system replied with "
        "today's forecast. Nothing to redact here, just plain text "
        "running through the regex pipeline. Pleasant weather expected."
    )
    text_with_pii = (
        "Contact alice@example.com or bob.smith+test@company.co.uk; "
        "phone +1 (555) 123-4567 or 555-987-6543. "
        "GitHub token ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789, "
        "AWS key AKIAIOSFODNN7EXAMPLE, "
        "Anthropic OAuth sk-ant-oat01-AbCdEfGhIjKlMnOpQrStUvWxYz_-1234567890. "
        "Plus a JWT eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.SflKxwRJSMeKKF2QT4f."
    )
    nested_payload = {
        "system_prompt": text_with_pii,
        "messages": [
            {"role": "user", "content": text_with_pii},
            {"role": "assistant", "content": plain_text},
            {"role": "user", "content": [
                {"type": "text", "text": text_with_pii},
                {"type": "text", "text": plain_text},
            ]},
        ],
        "tools_declared": ["web_search", "fetch_url"],
    }

    report(
        "redact(plain_text)",
        measure(lambda: redact(plain_text)),
        budget_us=500,
    )
    report(
        "redact(text_with_pii)",
        measure(lambda: redact(text_with_pii)),
        budget_us=500,
    )
    report(
        "redact_object(nested_payload)",
        measure(lambda: redact_object(nested_payload), n=2000),
        budget_us=2000,
    )


# ---------- BigQuery span mapping (ADR-0003) ----------


def bench_bq_processor() -> None:
    print("\n## BigQuery span processor (ADR-0003) — runs on every span finish")
    from gclaw.observability import bq_analytics

    def make_span(kind: str = "AGENT", with_pii_text: bool = False) -> MagicMock:
        span = MagicMock()
        span.name = "agent.research-mgr"
        attrs = {
            "openinference.span.kind": kind,
            "session.id": "sess-bench-1",
            "user.id": "user-bench-1",
            "graph.node.id": "research-mgr",
            "llm.model_name": "gemini-2.5-flash",
            "llm.provider": "google_vertex",
            "llm.token_count.prompt": 1234,
            "llm.token_count.completion": 567,
        }
        span.attributes = attrs
        span.context.trace_id = 0xABCDEF0123456789ABCDEF0123456789
        span.context.span_id = 0x0123456789ABCDEF
        span.parent = None
        span.start_time = 1_700_000_000_000_000_000
        span.end_time = 1_700_000_000_500_000_000
        status = MagicMock()
        status.status_code.name = "OK"
        status.description = None
        span.status = status
        return span

    writer = MagicMock(spec=bq_analytics.BigQueryAnalyticsWriter)
    proc = bq_analytics.BigQuerySpanProcessor(writer=writer)

    agent_span = make_span("AGENT")
    llm_span = make_span("LLM")
    tool_span = make_span("TOOL")

    report(
        "BigQuerySpanProcessor.on_end(AGENT)",
        measure(lambda: proc.on_end(agent_span)),
        budget_us=1000,
    )
    report(
        "BigQuerySpanProcessor.on_end(LLM)",
        measure(lambda: proc.on_end(llm_span)),
        budget_us=1000,
    )
    report(
        "BigQuerySpanProcessor.on_end(TOOL)",
        measure(lambda: proc.on_end(tool_span)),
        budget_us=1000,
    )


def bench_bq_writer_enqueue() -> None:
    print("\n## BigQuery writer enqueue (ADR-0003) — pure in-memory append")
    from gclaw.observability.bq_analytics import BigQueryAnalyticsWriter

    bq_client = MagicMock()
    bq_client.insert_rows_json.return_value = []
    bq_client.get_dataset.return_value = MagicMock()
    bq_client.get_table.return_value = MagicMock()
    writer = BigQueryAnalyticsWriter(
        project_id="bench-project",
        dataset="ds",
        table="tbl",
        bq_client=bq_client,
        flush_interval_seconds=1000.0,
        max_buffer_rows=10**9,  # never auto-flush during this bench
    )
    row = {
        "event_id": "0123456789abcdef",
        "trace_id": "abcdef0123456789abcdef0123456789",
        "agent_name": "research-mgr",
        "model": "gemini-2.5-flash",
        "input_tokens": 1234,
        "output_tokens": 567,
    }
    report(
        "BigQueryAnalyticsWriter.enqueue(row)",
        measure(lambda: writer.enqueue(row), n=10000),
        budget_us=200,
    )


# ---------- Prompt log payload assembly (ADR-0004) ----------


def bench_prompt_log_payload() -> None:
    print(
        "\n## Prompt log payload build (ADR-0004) — runs on every call_llm span"
    )
    from gclaw.observability import prompt_log as pl

    span = MagicMock()
    span.name = "llm.call"
    span.attributes = {
        "openinference.span.kind": "LLM",
        "llm.model_name": "claude-haiku-4-5",
        "llm.provider": "anthropic",
        "llm.input_messages.0.message.role": "system",
        "llm.input_messages.0.message.content": "You are a helpful assistant.",
        "llm.input_messages.1.message.role": "user",
        "llm.input_messages.1.message.content": (
            "Email me alice@example.com a summary of "
            "https://example.com/article and copy bob.smith@company.co"
        ),
        "llm.output_messages.0.message.role": "assistant",
        "llm.output_messages.0.message.content": (
            "Sure — drafting an email now to alice@example.com."
        ),
        "llm.token_count.prompt": 250,
        "llm.token_count.completion": 90,
        "session.id": "sess-bench",
        "user.id": "user-bench",
        "graph.node.id": "workspace-mgr",
    }
    span.context.trace_id = 0xABCDEF0123456789ABCDEF0123456789
    span.context.span_id = 0x0123456789ABCDEF
    span.start_time = 1_700_000_000_000_000_000
    span.end_time = 1_700_000_000_500_000_000

    attrs = dict(span.attributes)
    from datetime import datetime, timezone
    common = dict(
        attrs=attrs,
        event_id="0123456789abcdef",
        trace_id="abcdef0123456789abcdef0123456789",
        session_id="sess-bench",
        user_id="user-bench",
        agent_name="workspace-mgr",
        model="claude-haiku-4-5",
        provider="anthropic",
        when=datetime.now(timezone.utc),
    )

    report(
        "_build_prompt_payload",
        measure(lambda: pl._build_prompt_payload(**common)),
        budget_us=2000,
    )

    response_kwargs = dict(common)
    # _build_response_payload signature differs slightly — drop irrelevant
    # fields and add the response-specific ones if needed. Inspect at runtime.
    import inspect
    resp_params = set(
        inspect.signature(pl._build_response_payload).parameters.keys()
    )
    response_kwargs = {k: v for k, v in common.items() if k in resp_params}
    if "latency_ms" in resp_params:
        response_kwargs["latency_ms"] = 500
    if "span_start" in resp_params:
        response_kwargs["span_start"] = span.start_time
    if "span_end" in resp_params:
        response_kwargs["span_end"] = span.end_time
    report(
        "_build_response_payload",
        measure(lambda: pl._build_response_payload(**response_kwargs)),
        budget_us=2000,
    )


# ---------- Evalset (ADR-0005) ----------


def bench_eval_load_dump() -> None:
    print("\n## Evalset load + dump round-trip (ADR-0005)")
    from gclaw.eval.evalset import Evalset

    sample_path = "tests/eval/evalsets/research-mgr.json"
    with open(sample_path) as f:
        raw = f.read()

    def load_dump() -> None:
        ev = Evalset.model_validate_json(raw)
        ev.model_dump_json()

    report(
        "Evalset.load + dump",
        measure(load_dump, n=2000),
        budget_us=10_000,
    )


# ---------- Combined ----------


def main() -> None:
    print("=" * 70)
    print("OBSERVABILITY + EVAL HOT-PATH BENCHMARKS")
    print("Each hot path's budget is the wall-time we can afford WITHOUT")
    print("inflating chat latency past the ~50ms p99 promise.")
    print("=" * 70)

    bench_redaction()
    bench_bq_processor()
    bench_bq_writer_enqueue()
    bench_prompt_log_payload()
    bench_eval_load_dump()

    print("\nDone. See docs/perf/observability-bench.md for analysis.")


if __name__ == "__main__":
    main()
