"""LiveSpanProcessor fans AGENT spans to RunRegistry + Firestore repo."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock

import pytest

from gclaw.observability.live_span_processor import LiveSpanProcessor
from gclaw.observability.run_registry import RunRegistry


def _mk_span(
    *,
    name: str = "agent.orchestrator",
    kind: str = "AGENT",
    session_id: str = "s1",
    user_id: str = "u1",
    agent: str = "orchestrator",
    model: str | None = "gemini-2.5-flash",
    tokens_in: int | None = 100,
    tokens_out: int | None = 50,
):
    span = MagicMock()
    span.name = name
    span.attributes = {
        "openinference.span.kind": kind,
        "session.id": session_id,
        "user.id": user_id,
        "graph.node.id": agent,
        "llm.model_name": model,
        "llm.token_count.prompt": tokens_in,
        "llm.token_count.completion": tokens_out,
        "llm.token_count.total": (tokens_in or 0) + (tokens_out or 0),
    }
    span.context.trace_id = 0xABCDEF
    span.context.span_id = 0x123456
    span.start_time = 1
    span.end_time = 2
    status = MagicMock()
    status.status_code.name = "OK"
    span.status = status
    return span


@pytest.mark.asyncio
async def test_agent_span_enqueues_event():
    reg = RunRegistry()
    proc = LiveSpanProcessor(run_registry=reg)
    span = _mk_span()

    proc.on_end(span)

    q = await reg.subscribe("s1")
    event = await asyncio.wait_for(q.get(), timeout=0.5)
    assert event["event"] == "span.end"
    assert event["data"]["agent"] == "orchestrator"
    assert event["data"]["model_id"] == "gemini-2.5-flash"
    assert event["data"]["tokens"]["in"] == 100
    assert event["data"]["tokens"]["out"] == 50
    assert event["data"]["tokens"]["total"] == 150
    assert event["data"]["status"] == "OK"


@pytest.mark.asyncio
async def test_non_agent_span_is_ignored():
    reg = RunRegistry()
    proc = LiveSpanProcessor(run_registry=reg)
    span = _mk_span(kind="LLM")  # auto-instrumented LLM span

    proc.on_end(span)
    assert reg.stats() == {}


@pytest.mark.asyncio
async def test_missing_session_id_skips_fanout():
    reg = RunRegistry()
    repo = MagicMock()
    proc = LiveSpanProcessor(run_registry=reg, firestore_repo=repo)
    span = _mk_span(session_id="")

    proc.on_end(span)
    assert reg.stats() == {}
    repo.upsert.assert_not_called()


@pytest.mark.asyncio
async def test_firestore_upsert_is_throttled_per_run():
    """Throttle applies only to spans WITHOUT meaningful data.

    Sub-spans from ADK's OpenInference instrumentor end during a turn
    with SPAN_KIND=AGENT but no tokens / model — those are the ones
    worth throttling. Our root turn span at end-of-turn always carries
    tokens + model, and MUST land in Firestore regardless of how
    recently an upsert fired, otherwise the turn doc ends up with
    nulls everywhere.
    """
    reg = RunRegistry()
    repo = MagicMock()
    proc = LiveSpanProcessor(
        run_registry=reg, firestore_repo=repo, throttle_seconds=10.0
    )

    # Two empty-data spans — throttle should suppress the second.
    proc.on_end(_mk_span(model=None, tokens_in=None, tokens_out=None))
    proc.on_end(_mk_span(model=None, tokens_in=None, tokens_out=None))
    assert repo.upsert.call_count == 1

    # A meaningful span (tokens+model present) always writes, throttle
    # or not.
    proc.on_end(_mk_span())
    assert repo.upsert.call_count == 2

    # Another empty-data span within the window is still throttled —
    # the meaningful write above reset the window.
    proc.on_end(_mk_span(model=None, tokens_in=None, tokens_out=None))
    assert repo.upsert.call_count == 2

    # Forcibly age the window — empty-data write now goes through.
    proc._last_firestore_write["s1"] = time.monotonic() - 20
    proc.on_end(_mk_span(model=None, tokens_in=None, tokens_out=None))
    assert repo.upsert.call_count == 3


@pytest.mark.asyncio
async def test_on_end_swallows_repo_exceptions():
    reg = RunRegistry()
    repo = MagicMock()
    repo.upsert.side_effect = RuntimeError("firestore down")
    proc = LiveSpanProcessor(run_registry=reg, firestore_repo=repo)
    span = _mk_span()

    # Must not raise; event must still be enqueued.
    proc.on_end(span)
    q = await reg.subscribe("s1")
    assert q.qsize() == 1
