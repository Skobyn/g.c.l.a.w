"""Tests for the ADR-0003 BigQuery Agent Analytics writer + processor.

All BigQuery interaction is mocked — no real GCP calls.
"""

from __future__ import annotations

import asyncio
import os
from unittest.mock import MagicMock

import pytest

from gclaw.observability import bq_schema
from gclaw.observability.bq_analytics import (
    BigQueryAnalyticsWriter,
    BigQuerySpanProcessor,
)


# ── span helpers ───────────────────────────────────────────────────────


def _mk_span(
    *,
    kind: str = "AGENT",
    name: str = "agent.orchestrator",
    session_id: str = "sess-1",
    user_id: str = "user-1",
    agent_name: str = "orchestrator",
    model: str | None = "gemini-2.5-flash",
    provider: str | None = "google_vertex",
    tokens_in: int | None = 100,
    tokens_out: int | None = 200,
    tokens_cache: int | None = None,
    tool_name: str | None = None,
    error: bool = False,
    extra_attrs: dict | None = None,
):
    span = MagicMock()
    span.name = name
    attrs = {
        "openinference.span.kind": kind,
        "session.id": session_id,
        "user.id": user_id,
        "graph.node.id": agent_name,
    }
    if model is not None:
        attrs["llm.model_name"] = model
    if provider is not None:
        attrs["llm.provider"] = provider
    if tokens_in is not None:
        attrs["llm.token_count.prompt"] = tokens_in
    if tokens_out is not None:
        attrs["llm.token_count.completion"] = tokens_out
    if tokens_cache is not None:
        attrs["llm.token_count.cache_read"] = tokens_cache
    if tool_name is not None:
        attrs["tool.name"] = tool_name
    if extra_attrs:
        attrs.update(extra_attrs)
    span.attributes = attrs

    span.context.trace_id = 0xABCDEF0123456789ABCDEF0123456789
    span.context.span_id = 0x0123456789ABCDEF
    span.parent = None
    span.start_time = 1_700_000_000_000_000_000
    span.end_time = 1_700_000_000_500_000_000  # 500ms later

    status = MagicMock()
    status.status_code.name = "ERROR" if error else "OK"
    status.description = "boom" if error else None
    span.status = status
    return span


# ── 1. processor maps span to row ──────────────────────────────────────


def test_processor_maps_span_to_row():
    writer = MagicMock(spec=BigQueryAnalyticsWriter)
    proc = BigQuerySpanProcessor(writer=writer, cost_lookup=None)
    span = _mk_span()

    proc.on_end(span)

    writer.enqueue.assert_called_once()
    row = writer.enqueue.call_args[0][0]

    # Every documented column must be present.
    for col in bq_schema.column_names():
        assert col in row, f"missing column {col}"

    assert row[bq_schema.COL_EVENT_ID] == format(span.context.span_id, "016x")
    assert row[bq_schema.COL_TRACE_ID] == format(span.context.trace_id, "032x")
    assert row[bq_schema.COL_AGENT_NAME] == "orchestrator"
    assert row[bq_schema.COL_MODEL] == "gemini-2.5-flash"
    assert row[bq_schema.COL_PROVIDER] == "google_vertex"
    assert row[bq_schema.COL_INPUT_TOKENS] == 100
    assert row[bq_schema.COL_OUTPUT_TOKENS] == 200
    assert row[bq_schema.COL_USER_ID] == "user-1"
    assert row[bq_schema.COL_SESSION_ID] == "sess-1"
    assert row[bq_schema.COL_LATENCY_MS] == 500
    assert row[bq_schema.COL_EVENT_TYPE] == "agent_run"
    assert row[bq_schema.COL_COST_USD] is None  # no cost_lookup
    assert row[bq_schema.COL_ERROR_CLASS] is None
    # ISO 8601 with timezone
    assert "T" in row[bq_schema.COL_EVENT_TIME]
    assert row[bq_schema.COL_EVENT_TIME].endswith("+00:00")


def test_processor_maps_llm_span_to_call_llm_event():
    writer = MagicMock(spec=BigQueryAnalyticsWriter)
    proc = BigQuerySpanProcessor(writer=writer)
    proc.on_end(_mk_span(kind="LLM"))
    row = writer.enqueue.call_args[0][0]
    assert row[bq_schema.COL_EVENT_TYPE] == "call_llm"


def test_processor_maps_tool_span_to_execute_tool_event():
    writer = MagicMock(spec=BigQueryAnalyticsWriter)
    proc = BigQuerySpanProcessor(writer=writer)
    proc.on_end(_mk_span(kind="TOOL", tool_name="get_board_task"))
    row = writer.enqueue.call_args[0][0]
    assert row[bq_schema.COL_EVENT_TYPE] == "execute_tool"
    assert row[bq_schema.COL_TOOL_NAME] == "get_board_task"


def test_processor_falls_back_to_gen_ai_attrs_when_oi_missing():
    writer = MagicMock(spec=BigQueryAnalyticsWriter)
    proc = BigQuerySpanProcessor(writer=writer)
    span = _mk_span(
        model=None,
        provider=None,
        extra_attrs={
            "gen_ai.system": "anthropic",
            "gen_ai.request.model": "claude-haiku-4-5",
        },
    )
    proc.on_end(span)
    row = writer.enqueue.call_args[0][0]
    assert row[bq_schema.COL_MODEL] == "claude-haiku-4-5"
    assert row[bq_schema.COL_PROVIDER] == "anthropic"


def test_processor_records_error_state():
    writer = MagicMock(spec=BigQueryAnalyticsWriter)
    proc = BigQuerySpanProcessor(writer=writer)
    proc.on_end(_mk_span(error=True))
    row = writer.enqueue.call_args[0][0]
    assert row[bq_schema.COL_ERROR_CLASS] == "SpanError"
    assert row[bq_schema.COL_ERROR_MESSAGE] == "boom"


def test_processor_swallows_mapping_exceptions():
    """A span the processor can't parse must not propagate."""
    writer = MagicMock(spec=BigQueryAnalyticsWriter)
    proc = BigQuerySpanProcessor(writer=writer)
    bad_span = MagicMock()
    bad_span.attributes = None
    # Force the mapping to blow up by removing context resolution.
    type(bad_span).context = property(
        lambda self: (_ for _ in ()).throw(RuntimeError("no context"))
    )
    bad_span.start_time = None
    bad_span.end_time = None

    proc.on_end(bad_span)  # must not raise
    # Either a row was enqueued (resilient mapping) or none was — but
    # the call must have completed cleanly.


# ── 2. writer buffers and flushes ──────────────────────────────────────


@pytest.mark.asyncio
async def test_writer_buffers_and_flushes_on_size():
    """Hitting max_buffer_rows triggers an immediate flush."""
    bq_client = MagicMock()
    bq_client.insert_rows_json.return_value = []
    bq_client.get_dataset.return_value = MagicMock()
    bq_client.get_table.return_value = MagicMock()

    writer = BigQueryAnalyticsWriter(
        project_id="test-project",
        dataset="ds",
        table="tbl",
        bq_client=bq_client,
        flush_interval_seconds=10.0,  # interval is far away
        max_buffer_rows=3,
    )
    writer.start()
    try:
        for i in range(3):
            writer.enqueue({"event_id": str(i)})
        # Hand control to the event loop so the flush task runs.
        # Polling here rather than a fixed sleep keeps the test fast
        # while staying tolerant of CI thread-pool jitter. CI runners
        # have been observed to take >1s to schedule the flush task —
        # extend the budget to 5s before declaring failure.
        for _ in range(250):
            if bq_client.insert_rows_json.call_count >= 1:
                break
            await asyncio.sleep(0.02)
        assert bq_client.insert_rows_json.call_count >= 1
        rows = bq_client.insert_rows_json.call_args[0][1]
        assert len(rows) == 3
    finally:
        await writer.shutdown()


@pytest.mark.asyncio
async def test_writer_buffers_and_flushes_on_interval():
    """The periodic flush loop drains the buffer even below max size."""
    bq_client = MagicMock()
    bq_client.insert_rows_json.return_value = []
    bq_client.get_dataset.return_value = MagicMock()
    bq_client.get_table.return_value = MagicMock()

    writer = BigQueryAnalyticsWriter(
        project_id="test-project",
        dataset="ds",
        table="tbl",
        bq_client=bq_client,
        flush_interval_seconds=0.05,
        max_buffer_rows=1000,
    )
    writer.start()
    try:
        writer.enqueue({"event_id": "x"})
        # Wait long enough for at least one flush iteration.
        await asyncio.sleep(0.2)
        assert bq_client.insert_rows_json.call_count >= 1
    finally:
        await writer.shutdown()


# ── 3. writer falls open on BQ error ───────────────────────────────────


@pytest.mark.asyncio
async def test_writer_falls_open_on_bq_error():
    bq_client = MagicMock()
    bq_client.insert_rows_json.side_effect = RuntimeError("BQ down")
    bq_client.get_dataset.return_value = MagicMock()
    bq_client.get_table.return_value = MagicMock()

    writer = BigQueryAnalyticsWriter(
        project_id="test-project",
        dataset="ds",
        table="tbl",
        bq_client=bq_client,
        flush_interval_seconds=0.05,
        max_buffer_rows=1000,
    )
    writer.start()
    try:
        writer.enqueue({"event_id": "boom"})
        await asyncio.sleep(0.2)
        # Flush attempted, exception swallowed, nothing crashed.
        assert bq_client.insert_rows_json.call_count >= 1
    finally:
        await writer.shutdown()


@pytest.mark.asyncio
async def test_writer_drops_batch_on_slow_flush():
    """Flush hangs > FLUSH_TIMEOUT_SECONDS → batch is dropped, no crash."""
    bq_client = MagicMock()

    def _slow_insert(_table, _rows):
        # 3 seconds — comfortably past the 1s flush timeout.
        import time as _time

        _time.sleep(3)
        return []

    bq_client.insert_rows_json.side_effect = _slow_insert
    bq_client.get_dataset.return_value = MagicMock()
    bq_client.get_table.return_value = MagicMock()

    writer = BigQueryAnalyticsWriter(
        project_id="test-project",
        dataset="ds",
        table="tbl",
        bq_client=bq_client,
        flush_interval_seconds=0.05,
        max_buffer_rows=1000,
    )
    writer.start()
    try:
        writer.enqueue({"event_id": "slow"})
        # Wait past the 1s flush timeout but well under the BQ stub's
        # 3s sleep — the flush must time out cleanly.
        await asyncio.sleep(1.5)
    finally:
        await writer.shutdown()


# ── 4. cost computation uses catalog ───────────────────────────────────


def test_cost_computation_uses_catalog():
    writer = MagicMock(spec=BigQueryAnalyticsWriter)

    captured: dict = {}

    def _fake_lookup(model_id, tin, tout, *, tokens_cache_read=None):
        captured["args"] = (model_id, tin, tout, tokens_cache_read)
        # 100 in × $0.30/Mtok + 200 out × $2.50/Mtok
        return (100 * 0.30 + 200 * 2.50) / 1_000_000

    proc = BigQuerySpanProcessor(writer=writer, cost_lookup=_fake_lookup)
    proc.on_end(_mk_span())

    row = writer.enqueue.call_args[0][0]
    assert captured["args"] == ("gemini-2.5-flash", 100, 200, None)
    assert row[bq_schema.COL_COST_USD] is not None
    assert row[bq_schema.COL_COST_USD] == pytest.approx(
        (100 * 0.30 + 200 * 2.50) / 1_000_000
    )


def test_cost_computation_handles_lookup_without_cache_kwarg():
    """Older lookups don't accept ``tokens_cache_read=`` — processor falls back."""
    writer = MagicMock(spec=BigQueryAnalyticsWriter)

    def _legacy_lookup(model_id, tin, tout):
        return 0.000042

    proc = BigQuerySpanProcessor(writer=writer, cost_lookup=_legacy_lookup)
    proc.on_end(_mk_span())
    row = writer.enqueue.call_args[0][0]
    assert row[bq_schema.COL_COST_USD] == pytest.approx(0.000042)


def test_cost_is_null_when_lookup_returns_none():
    writer = MagicMock(spec=BigQueryAnalyticsWriter)

    def _no_cost(*_args, **_kwargs):
        return None

    proc = BigQuerySpanProcessor(writer=writer, cost_lookup=_no_cost)
    proc.on_end(_mk_span())
    row = writer.enqueue.call_args[0][0]
    assert row[bq_schema.COL_COST_USD] is None


def test_cost_is_null_without_model_or_tokens():
    writer = MagicMock(spec=BigQueryAnalyticsWriter)
    proc = BigQuerySpanProcessor(
        writer=writer, cost_lookup=lambda *a, **k: 1.0
    )
    proc.on_end(_mk_span(model=None, tokens_in=None, tokens_out=None))
    row = writer.enqueue.call_args[0][0]
    assert row[bq_schema.COL_COST_USD] is None


# ── 5. writer disabled when env false ──────────────────────────────────


def test_writer_disabled_when_env_false(monkeypatch):
    """Flag off → main.py never constructs a BQ client."""
    monkeypatch.setenv("BIGQUERY_ANALYTICS_ENABLED", "false")
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")

    from gclaw.settings import Settings

    s = Settings()
    assert s.bigquery_analytics_enabled is False
    # Defaults match the documented constants.
    assert s.bigquery_analytics_dataset == "gclaw_analytics"
    assert s.bigquery_analytics_table == "agent_events"


def test_writer_enabled_when_env_true(monkeypatch):
    monkeypatch.setenv("BIGQUERY_ANALYTICS_ENABLED", "true")
    monkeypatch.setenv("BIGQUERY_ANALYTICS_DATASET", "custom_ds")
    monkeypatch.setenv("BIGQUERY_ANALYTICS_TABLE", "custom_tbl")
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")

    from gclaw.settings import Settings

    s = Settings()
    assert s.bigquery_analytics_enabled is True
    assert s.bigquery_analytics_dataset == "custom_ds"
    assert s.bigquery_analytics_table == "custom_tbl"


# ── 6. schema includes all documented columns ──────────────────────────

# Columns the ADR-0003 schema table documents. If any is missing from
# bq_schema.schema_tuples(), the writer would emit a row dict that the
# auto-created table can't accept.
_ADR_DOCUMENTED_COLUMNS = {
    "event_id",
    "trace_id",
    "parent_event_id",
    "event_time",
    "event_type",
    "agent_name",
    "model",
    "provider",
    "tool_name",
    "tool_provenance",
    "latency_ms",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cost_usd",
    "user_id",
    "session_id",
    "prompt_uri",
    "response_uri",
    "error_class",
    "error_message",
    "attributes",
}


def test_schema_includes_all_documented_columns():
    declared = set(bq_schema.column_names())
    missing = _ADR_DOCUMENTED_COLUMNS - declared
    assert not missing, f"missing columns: {sorted(missing)}"


def test_schema_event_time_is_required_timestamp():
    """event_time is the partition key in BQ — must be REQUIRED TIMESTAMP."""
    by_name = {n: (t, m) for n, t, m in bq_schema.schema_tuples()}
    type_, mode = by_name["event_time"]
    assert type_ == "TIMESTAMP"
    assert mode == "REQUIRED"


def test_schema_cost_usd_is_float64():
    by_name = {n: (t, m) for n, t, m in bq_schema.schema_tuples()}
    type_, _mode = by_name["cost_usd"]
    assert type_ == "FLOAT64"


def test_schema_token_columns_are_int64():
    by_name = {n: (t, m) for n, t, m in bq_schema.schema_tuples()}
    for col in ("input_tokens", "output_tokens", "cache_read_tokens"):
        assert by_name[col][0] == "INT64", f"{col} should be INT64"


# ── 7. schema auto-creation is idempotent ──────────────────────────────


@pytest.mark.asyncio
async def test_writer_auto_creates_dataset_and_table(monkeypatch):
    """First flush calls get_dataset/get_table; if missing, create them."""
    from google.api_core.exceptions import NotFound

    bq_client = MagicMock()
    bq_client.get_dataset.side_effect = NotFound("nope")
    bq_client.get_table.side_effect = NotFound("nope")
    bq_client.insert_rows_json.return_value = []

    writer = BigQueryAnalyticsWriter(
        project_id="test-project",
        dataset="ds",
        table="tbl",
        bq_client=bq_client,
        flush_interval_seconds=0.05,
    )
    writer.start()
    try:
        writer.enqueue({"event_id": "x"})
        await asyncio.sleep(0.2)
        assert bq_client.create_dataset.called
        assert bq_client.create_table.called
        # A subsequent flush must NOT re-issue create_* calls.
        bq_client.create_dataset.reset_mock()
        bq_client.create_table.reset_mock()
        bq_client.get_dataset.side_effect = None
        bq_client.get_dataset.return_value = MagicMock()
        bq_client.get_table.side_effect = None
        bq_client.get_table.return_value = MagicMock()
        writer.enqueue({"event_id": "y"})
        await asyncio.sleep(0.2)
        assert not bq_client.create_dataset.called
        assert not bq_client.create_table.called
    finally:
        await writer.shutdown()
