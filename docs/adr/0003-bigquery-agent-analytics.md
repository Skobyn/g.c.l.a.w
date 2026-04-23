# ADR-0003: BigQuery Agent Analytics adoption

**Status:** Proposed (2026-04-22) — implementation pending
**Context:** Phoenix gives us live trace inspection but no
SQL-queryable analytics. We can't answer questions like "total LLM
spend per agent last 7 days" or "find every chat where the
orchestrator delegated to research-mgr and the response had a
hallucination flag" without standing up our own analytics pipeline.

## Decision

Adopt the BigQuery Agent Analytics schema from
`google/agents-cli`'s observability stack (which itself wraps ADK's
`BigQueryAgentAnalyticsPlugin`). Write events to a BigQuery dataset
in the deployment project, sourced from the same OpenTelemetry spans
that already feed Phoenix.

We do **not** install the upstream plugin verbatim — it assumes the
agents-cli scaffold layout and `AdkApp`. Instead, we implement a
small writer (`src/gclaw/observability/bq_analytics.py`) that:

1. Subscribes to the same span stream as our existing OTLP exporter.
2. Maps spans to the upstream's event schema (1:1 column compat).
3. Writes via the BigQuery Storage Write API (low latency, exactly-once).
4. Offloads multimodal content (images, audio) to GCS and stores the
   gs:// URI in the row, same as the upstream pattern.

Schema-compatibility means the same dashboards and SQL that work for
agents-cli projects work for ours. Future portability: if we ever
move an agent into an agents-cli scaffold, its history is queryable
in the same place.

## Schema (1:1 with agents-cli)

Single events table, partitioned by event time, clustered on
`agent_name` and `event_type`. Approximate columns (full upstream
schema in `https://adk.dev/integrations/bigquery-agent-analytics/`):

| Column | Type | Notes |
|---|---|---|
| `event_id` | STRING | Span ID |
| `trace_id` | STRING | OTel trace ID — joins to Phoenix |
| `parent_event_id` | STRING | For nested spans |
| `event_time` | TIMESTAMP | Partition key |
| `event_type` | STRING | `invocation` / `agent_run` / `call_llm` / `execute_tool` |
| `agent_name` | STRING | Cluster key |
| `model` | STRING | e.g. `gemini-2.5-flash`, `claude-haiku-4-5` |
| `provider` | STRING | `vertex` / `gemini-public` / `anthropic` / `copilot` |
| `tool_name` | STRING | NULL for non-tool events |
| `tool_provenance` | STRING | `LOCAL` / `MCP` / `SUB_AGENT` / `A2A` / `TRANSFER_AGENT` |
| `latency_ms` | INT64 |  |
| `input_tokens`, `output_tokens`, `cache_read_tokens` | INT64 |  |
| `cost_usd` | FLOAT64 | Computed from token counts × catalog pricing |
| `user_id` | STRING |  |
| `session_id` | STRING |  |
| `prompt_uri` | STRING | gs:// URI when offloaded; see ADR-0004 |
| `response_uri` | STRING | gs:// URI when offloaded |
| `error_class` | STRING | Exception type if span ended in error |
| `error_message` | STRING |  |
| `attributes` | JSON | Open-ended span attributes |

## Implementation plan

1. **Provision BQ dataset** (`gclaw_analytics`) + GCS bucket
   (`<project>-gclaw-analytics-blobs`) via the bootstrap script.
   Grant `gclaw-run-sa` `bigquery.dataEditor` on the dataset and
   `storage.objectAdmin` on the bucket.
2. **Add writer** at `src/gclaw/observability/bq_analytics.py`:
   - Wraps `google.cloud.bigquery_storage.BigQueryWriteAsyncClient`.
   - Buffers ~1s of events and flushes batches.
   - Falls open if BQ is unavailable — never blocks the agent path.
3. **Hook into the existing span pipeline**: add a span processor in
   `src/gclaw/observability/tracing.py` alongside the OTLP exporter.
   The processor maps spans to BQ rows. Both Phoenix and BQ get the
   same data.
4. **Cost computation**: use the catalog's `models.cost.input_per_mtok`
   / `output_per_mtok` fields. Already populated for
   `claude-haiku-4-5`, etc.; defaults to NULL when unknown.
5. **Sample queries**: ship a `docs/analytics-queries.md` with:
   - Spend per agent per day
   - p50/p95 latency per model
   - Tool-call frequency per agent
   - Hallucination-flagged responses (when ADR-0006 lands)
6. **Looker Studio template** (later): reuse Google's published
   template from agents-cli docs.

## Schema migrations

The upstream plugin advertises "auto-schema upgrade" — new optional
columns added without migration. We mirror that: writer always
includes the latest column set; rows from older deploys NULL out the
new columns. BQ permits adding nullable columns without rewriting the
table.

## What we do NOT do

- **Do not install the upstream `BigQueryAgentAnalyticsPlugin`
  directly.** Their plugin hooks ADK's runner via the agents-cli
  scaffold's `AdkApp`. We have our own runner (`AgentRunner`) and
  our own span pipeline. Implementing a thin writer keeps us in
  control of buffering, error handling, and where in the pipeline
  we tap.
- **Do not export to BQ from the test/local environment.** Writer is
  no-op when `GCP_PROJECT_ID` matches a local sentinel (e.g.
  `test-project`).

## Open questions

- **Retention** — start at 90 days; revisit if storage cost matters.
- **PII** — prompt/response URIs point at GCS. We need a redaction
  pass before writes; defer until ADR-0004 (which has the same
  question for the prompt-response log).

## Estimated cost

BigQuery: ~$0.02/GB stored, ~$5/TB queried. At gclaw's current load
(~100s of events/day) the dataset will be sub-1GB. Trivial.
GCS for blob offload: similar — a few MB/day at most.

## Dependencies

- ADR-0004 (prompt-response logging to GCS) writes the blobs that BQ
  rows reference. They can ship in parallel; the BQ writer treats
  the URI as opaque.
