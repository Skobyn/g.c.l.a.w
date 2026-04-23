"""BigQuery Agent Analytics writer (ADR-0003).

Two collaborators:

* :class:`BigQuerySpanProcessor` — an OTel ``SpanProcessor`` that
  inspects every span on ``on_end``, maps it to a row matching the
  schema in :mod:`gclaw.observability.bq_schema`, and hands it to the
  writer.
* :class:`BigQueryAnalyticsWriter` — buffers rows and flushes them to
  BigQuery on a background asyncio task. Buffering bounds: ~1s of
  rows, or ``max_buffer_rows`` (default 100), whichever trips first.

Both fail-open: every exception inside the BQ path is caught, logged
at WARNING, and the offending batch is dropped. The agent path never
blocks on a BQ call.

V1 implementation note
----------------------
The writer uses ``google.cloud.bigquery.Client.insert_rows_json`` for
v1. The Storage Write API (``BigQueryWriteAsyncClient``) is the
upstream-preferred path for low-latency exactly-once delivery, but
its ergonomics (proto schema management, AppendRowsStream lifecycle,
in-flight retries) are heavier than gclaw needs at ~100s of
events/day. Storage Write is a drop-in upgrade later — only the flush
implementation changes; the buffering, mapping, and error-handling
layers are stable.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any

from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor

from gclaw.observability import bq_schema
from gclaw.observability.constants import (
    GRAPH_NODE_ID,
    LLM_MODEL_NAME,
    LLM_PROVIDER,
    LLM_TOKEN_CACHE_READ,
    LLM_TOKEN_COMPLETION,
    LLM_TOKEN_PROMPT,
    SESSION_ID,
    TOOL_NAME,
    USER_ID,
)

logger = logging.getLogger(__name__)


_SPAN_KIND_KEY = "openinference.span.kind"
_SPAN_KIND_AGENT = "AGENT"
_SPAN_KIND_LLM = "LLM"
_SPAN_KIND_TOOL = "TOOL"

# OpenInference / OTel GenAI semantic-convention attribute names. Used
# as fallbacks when our internal ``llm.*`` keys aren't present (e.g.
# spans emitted by upstream instrumentors).
_GEN_AI_SYSTEM = "gen_ai.system"
_GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
_GEN_AI_RESPONSE_MODEL = "gen_ai.response.model"

# Default buffering bounds. Both can be overridden in the constructor.
_DEFAULT_FLUSH_INTERVAL_SECONDS = 1.0
_DEFAULT_MAX_BUFFER_ROWS = 100
# Hard cap on how long a single flush is allowed to take before we
# drop the batch and move on. Keeps the writer lively under BQ
# pathology.
_FLUSH_TIMEOUT_SECONDS = 1.0


class BigQueryAnalyticsWriter:
    """Buffers analytics rows and flushes them to BigQuery asynchronously.

    Construction is cheap — the BigQuery SDK client is built lazily on
    the first flush, and dataset/table existence is verified there
    too. That keeps the constructor safe to call before
    ``BIGQUERY_ANALYTICS_ENABLED`` has been honoured by the caller.
    """

    def __init__(
        self,
        *,
        project_id: str,
        dataset: str,
        table: str,
        bq_client: Any | None = None,
        flush_interval_seconds: float = _DEFAULT_FLUSH_INTERVAL_SECONDS,
        max_buffer_rows: int = _DEFAULT_MAX_BUFFER_ROWS,
    ) -> None:
        self._project_id = project_id
        self._dataset = dataset
        self._table = table
        self._flush_interval = flush_interval_seconds
        self._max_buffer = max_buffer_rows

        self._client = bq_client  # lazy-built when None
        self._client_lock = threading.Lock()
        self._schema_ready = False

        self._buffer: list[dict[str, Any]] = []
        self._buffer_lock = threading.Lock()
        self._first_buffered_at: float | None = None

        self._loop: asyncio.AbstractEventLoop | None = None
        self._flush_task: asyncio.Task | None = None
        self._closed = False

    # ── public API ──────────────────────────────────────────────────

    @property
    def table_ref(self) -> str:
        return f"{self._project_id}.{self._dataset}.{self._table}"

    def enqueue(self, row: dict[str, Any]) -> None:
        """Add a row to the buffer. Flushes synchronously if the buffer
        hits ``max_buffer_rows``.

        Safe to call from any thread or from inside a span-processor
        callback. Never raises.
        """
        try:
            should_flush = False
            with self._buffer_lock:
                self._buffer.append(row)
                if self._first_buffered_at is None:
                    self._first_buffered_at = time.monotonic()
                if len(self._buffer) >= self._max_buffer:
                    should_flush = True
            if should_flush:
                self._schedule_flush()
        except Exception:
            logger.warning(
                "bq-analytics: enqueue failed (swallowed)", exc_info=True
            )

    def start(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """Start the background flush loop.

        Safe to call multiple times — subsequent calls are no-ops. If
        ``loop`` is omitted, the current running loop is used. Must be
        called from a thread with an event loop already running, or
        with an explicit ``loop`` argument.
        """
        if self._flush_task is not None or self._closed:
            return
        try:
            if loop is None:
                # Prefer the actively running loop (the FastAPI lifespan
                # path). Fall back to ``get_event_loop`` for tests that
                # construct the writer outside an async context — but
                # never silently switch to a stale loop.
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = asyncio.get_event_loop()
            self._loop = loop
            self._flush_task = self._loop.create_task(self._flush_loop())
        except Exception:
            logger.warning(
                "bq-analytics: failed to start flush loop", exc_info=True
            )
            self._flush_task = None

    async def shutdown(self) -> None:
        """Drain the buffer and stop the flush loop."""
        self._closed = True
        if self._flush_task is not None:
            try:
                await self._flush_once()
            except Exception:
                logger.warning(
                    "bq-analytics: shutdown flush failed", exc_info=True
                )
            self._flush_task.cancel()
            try:
                await self._flush_task
            except (asyncio.CancelledError, Exception):
                pass
            self._flush_task = None

    # ── internals ───────────────────────────────────────────────────

    async def _flush_loop(self) -> None:
        while not self._closed:
            try:
                await asyncio.sleep(self._flush_interval)
                await self._flush_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning(
                    "bq-analytics: flush loop iteration failed",
                    exc_info=True,
                )

    def _schedule_flush(self) -> None:
        """Trigger a flush from outside the periodic loop.

        Safe to call from any thread or directly from inside the loop.
        When the writer hasn't been started, or the loop has died,
        this is a best-effort hint — we just leave the rows in the
        buffer for the next periodic flush rather than block the
        producer.
        """
        loop = self._loop
        if loop is None or not loop.is_running():
            return
        try:
            # When called from within the loop's own thread, schedule
            # the coroutine directly. From a worker thread, hop back
            # via call_soon_threadsafe — run_coroutine_threadsafe is
            # the cross-thread API but its blocking-future behaviour
            # confuses tests that assume "called from the loop".
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None
            if running is loop:
                loop.create_task(self._flush_once())
            else:
                loop.call_soon_threadsafe(
                    lambda: loop.create_task(self._flush_once())
                )
        except Exception:
            logger.warning(
                "bq-analytics: schedule_flush failed", exc_info=True
            )

    async def _flush_once(self) -> None:
        with self._buffer_lock:
            if not self._buffer:
                self._first_buffered_at = None
                return
            batch = self._buffer
            self._buffer = []
            self._first_buffered_at = None

        try:
            await asyncio.wait_for(
                asyncio.to_thread(self._write_batch, batch),
                timeout=_FLUSH_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "bq-analytics: flush exceeded %.1fs — dropped %d row(s)",
                _FLUSH_TIMEOUT_SECONDS,
                len(batch),
            )
        except Exception:
            logger.warning(
                "bq-analytics: flush failed — dropped %d row(s)",
                len(batch),
                exc_info=True,
            )

    def _write_batch(self, batch: list[dict[str, Any]]) -> None:
        client = self._ensure_client()
        if client is None:
            return
        self._ensure_schema(client)
        errors = client.insert_rows_json(self.table_ref, batch)
        if errors:
            logger.warning(
                "bq-analytics: insert_rows_json reported %d error(s): %s",
                len(errors),
                errors,
            )

    def _ensure_client(self) -> Any | None:
        if self._client is not None:
            return self._client
        with self._client_lock:
            if self._client is not None:
                return self._client
            try:
                from google.cloud import bigquery

                self._client = bigquery.Client(project=self._project_id)
            except Exception:
                logger.warning(
                    "bq-analytics: BigQuery client init failed",
                    exc_info=True,
                )
                self._client = None
        return self._client

    def _ensure_schema(self, client: Any) -> None:
        """Create the dataset + table if they don't already exist.

        Idempotent: ``Conflict`` on existing resources is treated as
        success. A failure here is logged and the next flush will try
        again — we don't burn the in-memory batch over a transient
        503 from the BigQuery control plane.
        """
        if self._schema_ready:
            return
        try:
            from google.api_core.exceptions import Conflict, NotFound
            from google.cloud import bigquery

            dataset_ref = bigquery.DatasetReference(
                self._project_id, self._dataset
            )
            try:
                client.get_dataset(dataset_ref)
            except NotFound:
                ds = bigquery.Dataset(dataset_ref)
                try:
                    client.create_dataset(ds)
                    logger.info(
                        "bq-analytics: created dataset %s", self._dataset
                    )
                except Conflict:
                    pass

            table_ref = dataset_ref.table(self._table)
            try:
                client.get_table(table_ref)
            except NotFound:
                table = bigquery.Table(
                    table_ref, schema=bq_schema.bigquery_schema()
                )
                try:
                    client.create_table(table)
                    logger.info(
                        "bq-analytics: created table %s", self.table_ref
                    )
                except Conflict:
                    pass
            self._schema_ready = True
        except Exception:
            logger.warning(
                "bq-analytics: ensure_schema failed", exc_info=True
            )


class BigQuerySpanProcessor(SpanProcessor):
    """OTel ``SpanProcessor`` that maps spans into BQ analytics rows.

    Registered alongside the Cloud Trace + OTLP exporters in
    :func:`gclaw.observability.tracing.init_tracing`. The processor is
    effectively a fan-out: spans continue to flow to Cloud Trace +
    Phoenix unchanged; we add a third sink for SQL analytics.

    ``cost_lookup`` matches the signature used elsewhere in the repo
    (``model_id, tokens_in, tokens_out, *, tokens_cache_read=None`` →
    ``float | None``). ``None`` means "unknown cost"; the writer
    leaves the column NULL in that case.
    """

    def __init__(
        self,
        *,
        writer: BigQueryAnalyticsWriter,
        cost_lookup: Any | None = None,
    ) -> None:
        self._writer = writer
        self._cost_lookup = cost_lookup

    # SpanProcessor protocol ------------------------------------------

    def on_start(
        self, span: Any, parent_context: Any | None = None
    ) -> None:
        return None

    def on_end(self, span: ReadableSpan) -> None:
        try:
            row = self._span_to_row(span)
            if row is not None:
                self._writer.enqueue(row)
        except Exception:
            logger.warning(
                "BigQuerySpanProcessor.on_end failed (swallowed)",
                exc_info=True,
            )

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True

    # mapping ----------------------------------------------------------

    def _span_to_row(self, span: ReadableSpan) -> dict[str, Any] | None:
        attrs = dict(span.attributes or {})

        kind_attr = attrs.get(_SPAN_KIND_KEY)
        event_type = _event_type_for_kind(kind_attr, span.name)

        tokens_in = _maybe_int(attrs.get(LLM_TOKEN_PROMPT))
        tokens_out = _maybe_int(attrs.get(LLM_TOKEN_COMPLETION))
        tokens_cache = _maybe_int(attrs.get(LLM_TOKEN_CACHE_READ))

        model = (
            attrs.get(LLM_MODEL_NAME)
            or attrs.get(_GEN_AI_RESPONSE_MODEL)
            or attrs.get(_GEN_AI_REQUEST_MODEL)
        )
        provider = attrs.get(LLM_PROVIDER) or attrs.get(_GEN_AI_SYSTEM)

        cost_usd: float | None = None
        if (
            self._cost_lookup is not None
            and model
            and (tokens_in is not None or tokens_out is not None)
        ):
            try:
                cost_usd = self._cost_lookup(
                    str(model),
                    int(tokens_in or 0),
                    int(tokens_out or 0),
                    tokens_cache_read=tokens_cache,
                )
            except TypeError:
                # Older lookups don't accept ``tokens_cache_read``.
                try:
                    cost_usd = self._cost_lookup(
                        str(model),
                        int(tokens_in or 0),
                        int(tokens_out or 0),
                    )
                except Exception:
                    cost_usd = None
            except Exception:
                cost_usd = None

        latency_ms = _latency_ms(span)
        error_class, error_message = _span_error(span)

        return {
            bq_schema.COL_EVENT_ID: _hex_span_id(span),
            bq_schema.COL_TRACE_ID: _hex_trace_id(span),
            bq_schema.COL_PARENT_EVENT_ID: _hex_parent_id(span),
            bq_schema.COL_EVENT_TIME: _iso_timestamp(span.end_time),
            bq_schema.COL_EVENT_TYPE: event_type,
            bq_schema.COL_AGENT_NAME: _str_or_none(attrs.get(GRAPH_NODE_ID)),
            bq_schema.COL_MODEL: _str_or_none(model),
            bq_schema.COL_PROVIDER: _str_or_none(provider),
            bq_schema.COL_TOOL_NAME: _str_or_none(attrs.get(TOOL_NAME)),
            bq_schema.COL_TOOL_PROVENANCE: _str_or_none(
                attrs.get("tool.provenance")
            ),
            bq_schema.COL_LATENCY_MS: latency_ms,
            bq_schema.COL_INPUT_TOKENS: tokens_in,
            bq_schema.COL_OUTPUT_TOKENS: tokens_out,
            bq_schema.COL_CACHE_READ_TOKENS: tokens_cache,
            bq_schema.COL_COST_USD: cost_usd,
            bq_schema.COL_USER_ID: _str_or_none(attrs.get(USER_ID)),
            bq_schema.COL_SESSION_ID: _str_or_none(attrs.get(SESSION_ID)),
            bq_schema.COL_PROMPT_URI: _str_or_none(attrs.get("prompt.uri")),
            bq_schema.COL_RESPONSE_URI: _str_or_none(
                attrs.get("response.uri")
            ),
            bq_schema.COL_ERROR_CLASS: error_class,
            bq_schema.COL_ERROR_MESSAGE: error_message,
            bq_schema.COL_ATTRIBUTES: _attributes_json(attrs),
        }


# ── helpers ────────────────────────────────────────────────────────────


def _event_type_for_kind(kind_attr: Any, span_name: str) -> str:
    if kind_attr == _SPAN_KIND_AGENT:
        return "agent_run"
    if kind_attr == _SPAN_KIND_LLM:
        return "call_llm"
    if kind_attr == _SPAN_KIND_TOOL:
        return "execute_tool"
    # Fallback: ADK's runner emits "invocation" wrapper spans without
    # an OpenInference kind attribute — keep the column populated so
    # the BQ rows are still groupable by event type.
    name = (span_name or "").lower()
    if "invocation" in name:
        return "invocation"
    return "other"


def _maybe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value)
    return s if s else None


def _hex_span_id(span: ReadableSpan) -> str:
    try:
        return format(span.context.span_id, "016x")
    except Exception:
        return ""


def _hex_trace_id(span: ReadableSpan) -> str:
    try:
        return format(span.context.trace_id, "032x")
    except Exception:
        return ""


def _hex_parent_id(span: ReadableSpan) -> str | None:
    parent = getattr(span, "parent", None)
    if parent is None:
        return None
    try:
        sid = getattr(parent, "span_id", None)
        if sid is None or sid == 0:
            return None
        return format(sid, "016x")
    except Exception:
        return None


def _iso_timestamp(end_time_ns: int | None) -> str:
    """OTel times are nanoseconds since epoch. BQ TIMESTAMP wants ISO 8601."""
    if not end_time_ns:
        end_time_ns = time.time_ns()
    seconds = end_time_ns / 1_000_000_000
    return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()


def _latency_ms(span: ReadableSpan) -> int | None:
    start = getattr(span, "start_time", None)
    end = getattr(span, "end_time", None)
    if start is None or end is None:
        return None
    try:
        return max(0, int((end - start) / 1_000_000))
    except Exception:
        return None


def _span_error(span: ReadableSpan) -> tuple[str | None, str | None]:
    status = getattr(span, "status", None)
    code = getattr(getattr(status, "status_code", None), "name", "")
    if code != "ERROR":
        return None, None
    description = getattr(status, "description", None)
    return "SpanError", _str_or_none(description) or "unknown"


def _attributes_json(attrs: dict[str, Any]) -> str | None:
    if not attrs:
        return None
    try:
        return json.dumps(attrs, default=str, sort_keys=True)
    except Exception:
        return None
