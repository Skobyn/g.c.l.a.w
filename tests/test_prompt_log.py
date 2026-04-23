"""Tests for the GCS prompt-response log writer + span processor (ADR-0004)."""

from __future__ import annotations

import json
from concurrent.futures import Future
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from gclaw.observability.prompt_log import (
    PromptLogSpanProcessor,
    PromptLogWriter,
    build_prompt_uri,
    build_response_uri,
)


# ── Helpers ──────────────────────────────────────────────────────────


def _mk_span(
    *,
    name: str = "call_llm",
    kind: str = "LLM",
    session_id: str = "sess-42",
    user_id: str = "user-1",
    agent: str = "research-mgr",
    model: str = "gemini-2.5-flash",
    provider: str = "google",
    system_prompt: str | None = "You are helpful.",
    user_message: str | None = "Find me a restaurant for scott@example.com",
    completion: str | None = "Here are 3 options",
    extra_attrs: dict | None = None,
):
    """Build a fake ReadableSpan with OpenInference-style attributes."""
    attrs: dict = {
        "openinference.span.kind": kind,
        "session.id": session_id,
        "user.id": user_id,
        "graph.node.id": agent,
        "llm.model_name": model,
        "llm.provider": provider,
        "llm.token_count.prompt": 123,
        "llm.token_count.completion": 45,
    }
    idx = 0
    if system_prompt is not None:
        attrs[f"llm.input_messages.{idx}.message.role"] = "system"
        attrs[f"llm.input_messages.{idx}.message.content"] = system_prompt
        idx += 1
    if user_message is not None:
        attrs[f"llm.input_messages.{idx}.message.role"] = "user"
        attrs[f"llm.input_messages.{idx}.message.content"] = user_message
        idx += 1
    if completion is not None:
        attrs["llm.output_messages.0.message.role"] = "assistant"
        attrs["llm.output_messages.0.message.content"] = completion
    if extra_attrs:
        attrs.update(extra_attrs)

    span = MagicMock()
    span.name = name
    span.attributes = attrs
    span.context.trace_id = 0xABCDEF1234567890_ABCDEF1234567890
    span.context.span_id = 0x1234567890ABCDEF
    # 2026-04-22T12:34:56Z as nanoseconds since epoch.
    end_dt = datetime(2026, 4, 22, 12, 34, 56, tzinfo=timezone.utc)
    span.end_time = int(end_dt.timestamp() * 1_000_000_000)
    span.start_time = span.end_time - 832_000_000  # 832ms earlier
    return span


def _completed_future(result=None) -> Future:
    f: Future = Future()
    f.set_result(result)
    return f


def _failed_future(exc: Exception) -> Future:
    f: Future = Future()
    f.set_exception(exc)
    return f


# ── URI helpers ──────────────────────────────────────────────────────


def test_build_prompt_uri_hive_format():
    uri = build_prompt_uri(
        bucket="my-bucket",
        when=datetime(2026, 4, 22, 22, 30, 1, tzinfo=timezone.utc),
        session_id="sess-1",
        event_id="evt-1",
    )
    assert uri == (
        "gs://my-bucket/yyyy=2026/mm=04/dd=22/hh=22/sess-1/evt-1.prompt.json"
    )


def test_build_response_uri_hive_format():
    uri = build_response_uri(
        bucket="my-bucket",
        when=datetime(2026, 4, 22, 22, 30, 1, tzinfo=timezone.utc),
        session_id="sess-1",
        event_id="evt-1",
    )
    assert uri.endswith("sess-1/evt-1.response.json")
    assert "yyyy=2026/mm=04/dd=22/hh=22" in uri


def test_uri_normalizes_to_utc():
    # A non-UTC datetime should still produce hour=22 (UTC).
    from datetime import timedelta, timezone as _tz

    pacific = _tz(timedelta(hours=-7))
    when = datetime(2026, 4, 22, 15, 30, 1, tzinfo=pacific)
    uri = build_prompt_uri(
        bucket="b", when=when, session_id="s", event_id="e"
    )
    assert "hh=22" in uri


# ── Writer ───────────────────────────────────────────────────────────


def test_writer_uploads_two_blobs():
    """Span with prompt + completion → two GCS uploads (mocked)."""
    mock_blob = MagicMock()
    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_client = MagicMock()
    mock_client.bucket.return_value = mock_bucket

    with patch(
        "google.cloud.storage.Client", return_value=mock_client
    ):
        writer = PromptLogWriter(
            bucket_name="prompt-log", project="test-proj"
        )
        # Submit synchronously by stubbing the executor.
        writer._executor = MagicMock()
        writer._executor.submit.return_value = _completed_future()

        prompt_uri, response_uri = writer.upload_pair(
            when=datetime(2026, 4, 22, 22, 30, 1, tzinfo=timezone.utc),
            session_id="s1",
            event_id="e1",
            prompt={"foo": "bar"},
            response={"baz": "qux"},
        )

    assert prompt_uri.endswith("s1/e1.prompt.json")
    assert response_uri.endswith("s1/e1.response.json")
    # Two submits — one per blob.
    assert writer._executor.submit.call_count == 2


def test_writer_path_follows_hive_partition():
    """Submitted blob names match the URI shape."""
    mock_executor = MagicMock()
    mock_executor.submit.return_value = _completed_future()

    writer = PromptLogWriter(bucket_name="bucket-x", project="p")
    writer._executor = mock_executor

    writer.upload_pair(
        when=datetime(2026, 1, 5, 9, 0, 0, tzinfo=timezone.utc),
        session_id="sess-A",
        event_id="evt-Z",
        prompt={"a": 1},
        response={"b": 2},
    )

    # Each submit call: (upload_func, name, payload_bytes)
    calls = mock_executor.submit.call_args_list
    names = [c.args[1] for c in calls]
    assert names[0] == (
        "yyyy=2026/mm=01/dd=05/hh=09/sess-A/evt-Z.prompt.json"
    )
    assert names[1] == (
        "yyyy=2026/mm=01/dd=05/hh=09/sess-A/evt-Z.response.json"
    )

    # Payloads are JSON-encoded.
    prompt_payload = json.loads(calls[0].args[2].decode("utf-8"))
    assert prompt_payload == {"a": 1}


def test_writer_swallows_gcs_errors():
    """Upload failures are caught + logged, never re-raised."""
    failing_executor = MagicMock()
    failing_executor.submit.return_value = _failed_future(
        RuntimeError("503 service unavailable")
    )

    writer = PromptLogWriter(bucket_name="b", project="p")
    writer._executor = failing_executor

    # Must not raise.
    writer.upload_pair(
        when=datetime(2026, 4, 22, 0, 0, 0, tzinfo=timezone.utc),
        session_id="s",
        event_id="e",
        prompt={"x": 1},
        response={"y": 2},
    )


# ── Span processor ──────────────────────────────────────────────────


def test_processor_dispatches_call_llm_span():
    writer = MagicMock(spec=PromptLogWriter)
    proc = PromptLogSpanProcessor(writer=writer)

    proc.on_end(_mk_span())

    writer.upload_pair.assert_called_once()
    kwargs = writer.upload_pair.call_args.kwargs
    assert kwargs["session_id"] == "sess-42"
    assert kwargs["event_id"] == format(0x1234567890ABCDEF, "016x")
    prompt = kwargs["prompt"]
    assert prompt["agent_name"] == "research-mgr"
    assert prompt["model"] == "gemini-2.5-flash"
    assert prompt["system_prompt"] == "You are helpful."
    assert prompt["messages"][0]["role"] == "user"
    response = kwargs["response"]
    assert response["input_tokens"] == 123
    assert response["output_tokens"] == 45
    assert response["latency_ms"] == 832


def test_processor_ignores_non_llm_span():
    """Span without LLM kind / call_llm name is ignored."""
    writer = MagicMock(spec=PromptLogWriter)
    proc = PromptLogSpanProcessor(writer=writer)

    span = _mk_span(name="agent.run", kind="AGENT")
    proc.on_end(span)

    writer.upload_pair.assert_not_called()


def test_processor_swallows_writer_exception():
    """Writer errors in on_end never propagate."""
    writer = MagicMock(spec=PromptLogWriter)
    writer.upload_pair.side_effect = RuntimeError("gcs down")
    proc = PromptLogSpanProcessor(writer=writer)

    # Must not raise.
    proc.on_end(_mk_span())


def test_processor_redacts_before_upload():
    """PII / secrets are redacted in payloads handed to the writer."""
    writer = MagicMock(spec=PromptLogWriter)
    proc = PromptLogSpanProcessor(writer=writer)

    proc.on_end(
        _mk_span(
            user_message="My email is user@example.com",
            completion="Reply to AKIAIOSFODNN7EXAMPLE soon",
        )
    )

    kwargs = writer.upload_pair.call_args.kwargs
    prompt_blob = json.dumps(kwargs["prompt"])
    response_blob = json.dumps(kwargs["response"])

    assert "user@example.com" not in prompt_blob
    assert "<REDACTED:email>" in prompt_blob
    assert "AKIAIOSFODNN7EXAMPLE" not in response_blob
    assert "<REDACTED:aws_access_key>" in response_blob


def test_processor_falls_back_to_gen_ai_attrs():
    """When llm.input_messages.* is absent, gen_ai.prompt is used."""
    writer = MagicMock(spec=PromptLogWriter)
    proc = PromptLogSpanProcessor(writer=writer)

    span = _mk_span(
        system_prompt=None,
        user_message=None,
        completion=None,
        extra_attrs={
            "gen_ai.prompt": "raw prompt body",
            "gen_ai.completion": "raw completion body",
        },
    )
    proc.on_end(span)

    kwargs = writer.upload_pair.call_args.kwargs
    assert kwargs["prompt"]["messages"][0]["content"] == "raw prompt body"
    assert kwargs["response"]["response_text"] == "raw completion body"


# ── Disabled (settings) integration ─────────────────────────────────


def test_writer_not_constructed_when_disabled(monkeypatch):
    """When PROMPT_LOG_ENABLED=false, main.py never instantiates the writer."""
    # Verify by inspecting settings — the actual wiring is in main.py
    # which we can't instantiate here without a full GCP env, but we
    # can confirm the toggle defaults off.
    monkeypatch.delenv("PROMPT_LOG_ENABLED", raising=False)
    monkeypatch.setenv("GCP_PROJECT_ID", "test-proj")
    from gclaw.settings import get_settings

    s = get_settings()
    assert s.prompt_log_enabled is False
    assert s.prompt_log_bucket == ""


def test_writer_enabled_with_bucket(monkeypatch):
    monkeypatch.setenv("PROMPT_LOG_ENABLED", "true")
    monkeypatch.setenv("PROMPT_LOG_BUCKET", "my-prompt-log")
    monkeypatch.setenv("GCP_PROJECT_ID", "test-proj")
    from gclaw.settings import get_settings

    s = get_settings()
    assert s.prompt_log_enabled is True
    assert s.prompt_log_bucket == "my-prompt-log"


# ── No-call path: writer mocked, never touches real GCS ─────────────


def test_writer_lazy_client_construction():
    """The GCS client is built only on first upload, not at construction."""
    writer = PromptLogWriter(bucket_name="b", project="p")
    # _client unset means we never reached out to google.cloud.storage.
    assert writer._client is None


@pytest.mark.parametrize("missing", ["session.id", "user.id"])
def test_processor_handles_missing_identity_attrs(missing):
    """Missing session/user attrs don't blow up — fall back to defaults."""
    writer = MagicMock(spec=PromptLogWriter)
    proc = PromptLogSpanProcessor(writer=writer)

    span = _mk_span()
    span.attributes = {k: v for k, v in span.attributes.items() if k != missing}
    proc.on_end(span)

    writer.upload_pair.assert_called_once()
