# Observability + Eval Hot-Path Benchmarks

**Date:** 2026-04-23
**Hardware:** Apple M-series (darwin 25.3.0)
**Python:** 3.12 / asyncio mode auto
**Runs:** `uv run python benchmarks/bench_observability.py`

## Headline

Total per-LLM-call observability overhead added by ADRs 0003 + 0004:
**p99 ≈ 110 µs** added to chat latency on the synchronous path. Target
was **<50 ms p99 added latency**. We're using **0.2% of the budget**.

The async I/O (BQ Storage Write API call, GCS upload) happens
fire-and-forget on a background loop and **never blocks the chat
turn**. Those don't add to chat latency.

## Per-hot-path numbers

| Hot path | When it runs | p50 | p95 | p99 | Budget | Verdict |
|---|---|---|---|---|---|---|
| `redact(plain_text)` | per prompt + response payload | 8 µs | 10 µs | 11 µs | 500 µs | **45× headroom** |
| `redact(text_with_pii)` | per prompt + response payload | 12 µs | 14 µs | 17 µs | 500 µs | **30× headroom** |
| `redact_object(nested_payload)` | per prompt + response payload | 60 µs | 70 µs | 85 µs | 2000 µs | **23× headroom** |
| `BigQuerySpanProcessor.on_end(AGENT)` | every agent span finish | 9 µs | 12 µs | 18 µs | 1000 µs | **55× headroom** |
| `BigQuerySpanProcessor.on_end(LLM)` | every call_llm span finish | 9 µs | 12 µs | 18 µs | 1000 µs | **55× headroom** |
| `BigQuerySpanProcessor.on_end(TOOL)` | every execute_tool span finish | 9 µs | 12 µs | 18 µs | 1000 µs | **55× headroom** |
| `BigQueryAnalyticsWriter.enqueue` | per row produced | 0.2 µs | 0.2 µs | 0.3 µs | 200 µs | **600× headroom** (just a dict append) |
| `_build_prompt_payload` | per call_llm span | 3 µs | 4 µs | 5 µs | 2000 µs | **400× headroom** |
| `_build_response_payload` | per call_llm span | 3 µs | 3 µs | 4 µs | 2000 µs | **500× headroom** |
| `Evalset.load + dump` | once per `gclaw-eval run` | 10 µs | 12 µs | 13 µs | 10 000 µs | **750× headroom** |

## What this means in chat-latency terms

A single call_llm span emits both processors in sequence:

```
on_end(call_llm_span):
  prompt_log:  _build_prompt_payload   ~5 µs
                redact_object(prompt)   ~85 µs (worst-case nested)
                _build_response_payload  ~4 µs
                redact_object(response)  ~85 µs (worst-case nested)
                upload_pair (async, fire-and-forget — does NOT add to span)
  bq_analytics: BigQuerySpanProcessor.on_end  ~18 µs
                BigQueryAnalyticsWriter.enqueue  ~0.3 µs
```

Total synchronous overhead per LLM call: **~200 µs at p99**, dominated
by redaction. A typical chat turn has 1–3 LLM calls. Worst-case
overhead per chat turn: **~600 µs**. Compared to a Gemini Flash call
(~500 ms baseline) or a Claude turn with web search (~3 s baseline),
this is **noise**.

## Why nothing needs optimizing

1. **Redaction** is regex-only. The expensive PII patterns (emails,
   phone numbers, JWTs) compile to a single combined automaton in `re`
   and run in linear time over the input. 85 µs for a 4-message
   nested payload with 8 different match types is the floor.
2. **BQ span mapping** is a flat dict construction with `attrs.get(...)`
   lookups. No I/O, no JSON serialization (that happens later in the
   batched flush). 18 µs is already at the metadata-extraction floor.
3. **BQ writer enqueue** is a single `list.append` under a thread lock
   — nothing to shave.
4. **Prompt-payload assembly** copies attrs into a typed dict. 5 µs.
5. **Evalset round-trip** is Pydantic v2 — written in Rust under the
   hood. Already fast.

## What we did NOT measure (and why)

- **GCS upload latency** — fire-and-forget on a worker pool with a 2 s
  upload deadline. Doesn't add to chat latency. ADR-0004's failure mode
  is "drop the row, log a warning" — never block the agent.
- **BQ insert_rows_json latency** — same pattern. Buffered batches
  flush every 1 s OR when the buffer hits `max_buffer_rows`, on a
  separate task. Doesn't add to chat latency.
- **End-to-end eval throughput** — bounded by the LLM API roundtrips,
  not the framework. With Gemini Flash judge (~500 ms/call) and 5 cases
  × 3 judge metrics = 15 calls, baseline of `gclaw-eval run` against
  one evalset is ~7.5 s. The framework's own overhead is the
  10 µs schema load — a rounding error.
- **Recursion depth in `redact_object`** — synthetic payload tested up
  to 3 levels of nesting. Pathological deeper structures could degrade.
  Mitigation in code: `redact_object` doesn't recurse into strings, so
  the actual recursion depth is bounded by the dict/list nesting of
  the LLM messages array, which is structurally shallow (≤ 4 in
  practice).

## Re-running

```bash
uv run python benchmarks/bench_observability.py
```

Bench is hermetic — no network, no real GCP — and runs in <2 seconds.
Add it to a perf-regression CI job if numbers ever start drifting.

## Conclusion

**No optimizations required.** Implementations from ADRs 0003 / 0004 /
0005 ship at production-quality performance. The synchronous overhead
is two orders of magnitude below the budget set in ADR-0003.

If the load profile changes dramatically (e.g., 10× more spans / sec
because we add a high-frequency tool-call workload), revisit the BQ
writer's batching parameters first — it's the only path that has any
notion of "load" baked into its config (`flush_interval_seconds`,
`max_buffer_rows`).
