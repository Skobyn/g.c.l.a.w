"""BigQuery Agent Analytics — declarative table schema.

Mirrors the column set documented in ADR-0003. Centralising the schema
here means:

  * The writer (:mod:`gclaw.observability.bq_analytics`) can use it to
    auto-create the destination table on first flush.
  * Tests can assert that every column listed in the ADR is present
    without reaching into BQ-specific types.
  * Schema migrations stay a single-file edit — append a new
    ``SchemaField(..., mode="NULLABLE")`` and re-deploy. BigQuery
    accepts nullable additions without a rewrite, so older deploys
    co-exist with newer ones (rows just NULL out the new column).

Importing this module never touches the network.
"""

from __future__ import annotations

# Column names exposed as constants so tests + the writer can reference
# the same literals without typo risk.
COL_EVENT_ID = "event_id"
COL_TRACE_ID = "trace_id"
COL_PARENT_EVENT_ID = "parent_event_id"
COL_EVENT_TIME = "event_time"
COL_EVENT_TYPE = "event_type"
COL_AGENT_NAME = "agent_name"
COL_MODEL = "model"
COL_PROVIDER = "provider"
COL_TOOL_NAME = "tool_name"
COL_TOOL_PROVENANCE = "tool_provenance"
COL_LATENCY_MS = "latency_ms"
COL_INPUT_TOKENS = "input_tokens"
COL_OUTPUT_TOKENS = "output_tokens"
COL_CACHE_READ_TOKENS = "cache_read_tokens"
COL_COST_USD = "cost_usd"
COL_USER_ID = "user_id"
COL_SESSION_ID = "session_id"
COL_PROMPT_URI = "prompt_uri"
COL_RESPONSE_URI = "response_uri"
COL_ERROR_CLASS = "error_class"
COL_ERROR_MESSAGE = "error_message"
COL_ATTRIBUTES = "attributes"


# (name, type, mode) tuples — the writer turns these into
# ``bigquery.SchemaField`` objects at table-creation time, and tests
# assert against the tuples directly so they don't need the BQ SDK.
_SCHEMA_TUPLES: tuple[tuple[str, str, str], ...] = (
    (COL_EVENT_ID, "STRING", "REQUIRED"),
    (COL_TRACE_ID, "STRING", "NULLABLE"),
    (COL_PARENT_EVENT_ID, "STRING", "NULLABLE"),
    (COL_EVENT_TIME, "TIMESTAMP", "REQUIRED"),
    (COL_EVENT_TYPE, "STRING", "NULLABLE"),
    (COL_AGENT_NAME, "STRING", "NULLABLE"),
    (COL_MODEL, "STRING", "NULLABLE"),
    (COL_PROVIDER, "STRING", "NULLABLE"),
    (COL_TOOL_NAME, "STRING", "NULLABLE"),
    (COL_TOOL_PROVENANCE, "STRING", "NULLABLE"),
    (COL_LATENCY_MS, "INT64", "NULLABLE"),
    (COL_INPUT_TOKENS, "INT64", "NULLABLE"),
    (COL_OUTPUT_TOKENS, "INT64", "NULLABLE"),
    (COL_CACHE_READ_TOKENS, "INT64", "NULLABLE"),
    (COL_COST_USD, "FLOAT64", "NULLABLE"),
    (COL_USER_ID, "STRING", "NULLABLE"),
    (COL_SESSION_ID, "STRING", "NULLABLE"),
    (COL_PROMPT_URI, "STRING", "NULLABLE"),
    (COL_RESPONSE_URI, "STRING", "NULLABLE"),
    (COL_ERROR_CLASS, "STRING", "NULLABLE"),
    (COL_ERROR_MESSAGE, "STRING", "NULLABLE"),
    (COL_ATTRIBUTES, "JSON", "NULLABLE"),
)


def schema_tuples() -> tuple[tuple[str, str, str], ...]:
    """Return the ``(name, type, mode)`` tuple for each column.

    Stable across releases — append-only.
    """
    return _SCHEMA_TUPLES


def column_names() -> tuple[str, ...]:
    """Return just the column names, in declaration order."""
    return tuple(name for name, _type, _mode in _SCHEMA_TUPLES)


def bigquery_schema() -> list:
    """Return a list of ``bigquery.SchemaField`` objects.

    Imports the BQ SDK lazily so test code that only inspects column
    metadata doesn't have to install ``google-cloud-bigquery``.
    """
    from google.cloud import bigquery

    return [
        bigquery.SchemaField(name, type_, mode=mode)
        for name, type_, mode in _SCHEMA_TUPLES
    ]
