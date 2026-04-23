# ADR-0004: Prompt-response logging to GCS

**Status:** Proposed (2026-04-22) — implementation pending
**Context:** Today we have OpenTelemetry spans with input/output text
in span attributes. Phoenix renders them in the trace viewer. There's
no audit log: no per-LLM-call record archived for replay, no
SQL-joinable record of what was actually said, no compliance trail.
agents-cli's "Prompt-Response Logging" tier solves this by writing
each LLM call's full input and output to GCS + BigQuery + Cloud
Logging, schema-aligned with their BigQuery Analytics dataset.

## Decision

Adopt a GCS-backed prompt-response log mirroring agents-cli's shape.
Each LLM call produces one JSON object written to a partitioned GCS
path. The corresponding BQ analytics row (ADR-0003) gets the
`prompt_uri` / `response_uri` columns populated so a SQL join
recovers the full text.

Path layout (mirrors upstream):

```
gs://<project>-gclaw-prompt-log/
  yyyy=2026/mm=04/dd=22/hh=22/
    <session_id>/<event_id>.prompt.json
    <session_id>/<event_id>.response.json
```

Hive-partitioned so BQ external tables (or `bq load`) can scan a
specific time range without listing the whole bucket.

## Schema

`<event_id>.prompt.json`:

```json
{
  "event_id": "...",
  "trace_id": "...",
  "session_id": "...",
  "user_id": "...",
  "agent_name": "research-mgr",
  "model": "claude-haiku-4-5",
  "provider": "anthropic",
  "system_prompt": "...",
  "messages": [{"role": "user", "content": "..."}],
  "tools_declared": ["web_search", "fetch_url"],
  "request_at": "2026-04-22T22:30:01.123Z"
}
```

`<event_id>.response.json`:

```json
{
  "event_id": "...",
  "trace_id": "...",
  "response_text": "...",
  "tool_calls": [{"name": "web_search", "args": {...}}],
  "stop_reason": "tool_use",
  "input_tokens": 1234,
  "output_tokens": 56,
  "latency_ms": 832,
  "response_at": "2026-04-22T22:30:01.955Z"
}
```

Two files per call instead of one because the prompt is sometimes
huge (system + history) and the response is small — separation makes
"replay just the prompt" cheap.

## Implementation plan

1. **Bucket** — `<project>-gclaw-prompt-log` provisioned by the
   bootstrap script. Lifecycle rule: archive after 30 days, delete
   after 365. Enable bucket-level uniform access; restrict to
   `gclaw-run-sa` (write) and the analyst group (read).
2. **Writer** at `src/gclaw/observability/prompt_log.py`:
   - Subscribes to the same span pipeline as ADR-0003.
   - On `call_llm` span finish: serializes prompt + response, uploads
     async to GCS.
   - Returns the URI to the BQ writer so it lands in the same row.
   - Falls open on GCS errors — log a warning, never block the chat.
3. **PII gate** — see "Redaction" below.
4. **Toggle** — env `PROMPT_LOG_ENABLED` (default `false`). On in
   prod, off locally.
5. **Cloud Logging mirror** (optional, deferred): also write to
   `agent-prompt-log` log name. Useful for short-term debugging via
   Cloud Logs Explorer; redundant with BQ for analysis.

## Redaction

Real risk: prompts and responses include user emails, calendar
contents, file contents, etc. Storing them in GCS for a year is a
data-protection issue.

Phase 1 (ship): redact known patterns before write — emails (regex
`[\w.+-]+@[\w-]+\.[\w.-]+`), phone numbers, GCP secret-manager
references, anything that matches AWS / GitHub / Anthropic / OpenAI
key shapes. Replace with `<REDACTED:type>`. The redaction module
lives next to the writer so it's easy to test.

Phase 2 (later): integrate Cloud DLP for richer detection. Out of
scope for the initial PR.

## Toggle matrix

| Env | `PROMPT_LOG_ENABLED` | Effect |
|---|---|---|
| local dev | `false` (default) | No GCS writes; BQ writer NULLs out URI columns |
| staging | `true` | Full logging |
| prod | `true` (eventually) | Full logging with redaction |

## What we do NOT do

- **Don't capture full multimodal blobs inline.** Images / audio
  already live in their own GCS buckets via the content pipeline.
  Reference by URI; don't duplicate.
- **Don't backfill historical logs.** ADR scope is forward-only.
  Prior chat history is in Firestore session records; if we ever
  need them in this format, write a one-off migration script.

## Dependencies

- ADR-0003 (BQ Analytics) writes the row that points to these GCS
  objects. The two should ship together; either alone is half-useful.

## Estimated cost

GCS: ~$0.02/GB-month standard, $0.004/GB-month archive. At
~10MB/day prompt+response volume, ~3.5GB/year — pennies.
Network egress only when reading for replay.
