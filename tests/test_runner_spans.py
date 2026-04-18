"""AgentRunner emits an AGENT-kind OpenInference span per turn.

Uses the OTel SDK's in-memory exporter so we can assert span names and
attributes without touching Cloud Trace. The exporter attaches to
whatever TracerProvider is currently installed — in a full pytest run
that will be the one set up by test_tracing_init.py, in isolation it's
a fresh SDK provider installed by this module's fixture.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gclaw.dispatch.runner import AgentRunner


def _event(text=None, func_name=None, func_args=None, usage=None,
           final=False, model_version=None):
    ev = MagicMock()
    ev.is_final_response.return_value = final
    parts = []
    if text:
        p = MagicMock()
        p.text = text
        p.function_call = None
        parts.append(p)
    if func_name:
        p = MagicMock()
        p.text = None
        fc = MagicMock()
        fc.name = func_name
        fc.args = func_args or {}
        p.function_call = fc
        parts.append(p)
    ev.content = MagicMock()
    ev.content.parts = parts or None
    ev.usage_metadata = usage
    ev.model_version = model_version
    return ev


@pytest.fixture
def captured_spans():
    """Attach an InMemorySpanExporter to the active tracer provider."""
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    existing = trace.get_tracer_provider()
    if not isinstance(existing, TracerProvider):
        trace.set_tracer_provider(TracerProvider())
        existing = trace.get_tracer_provider()

    exporter = InMemorySpanExporter()
    existing.add_span_processor(SimpleSpanProcessor(exporter))
    yield exporter
    exporter.clear()


@pytest.mark.asyncio
async def test_run_emits_agent_span_with_identity_attrs(captured_spans):
    agent = MagicMock()
    agent.name = "orchestrator"
    session_service = AsyncMock()

    usage_meta = MagicMock()
    usage_meta.prompt_token_count = 42
    usage_meta.candidates_token_count = 7

    events = [
        _event(text="hi", usage=usage_meta, model_version="gemini-2.5-flash"),
        _event(final=True),
    ]

    async def fake_run(**_):
        for e in events:
            yield e

    with patch("gclaw.dispatch.runner.Runner") as MockRunner:
        MockRunner.return_value.run_async = fake_run
        runner = AgentRunner(
            agent=agent,
            app_name="gclaw",
            session_service=session_service,
        )
        await runner.run(user_id="u1", session_id="s1", message="hello")

    spans = [s for s in captured_spans.get_finished_spans()
             if s.name == "agent.orchestrator"]
    assert len(spans) == 1
    span = spans[0]
    attrs = dict(span.attributes or {})
    assert attrs.get("openinference.span.kind") == "AGENT"
    assert attrs.get("graph.node.id") == "orchestrator"
    assert attrs.get("session.id") == "s1"
    assert attrs.get("user.id") == "u1"
    assert attrs.get("llm.model_name") == "gemini-2.5-flash"
    assert attrs.get("llm.token_count.prompt") == 42
    assert attrs.get("llm.token_count.completion") == 7
    assert attrs.get("llm.token_count.total") == 49


@pytest.mark.asyncio
async def test_run_records_exception_on_span(captured_spans):
    """Non-retryable failures still get a span with an ERROR status."""
    agent = MagicMock()
    agent.name = "orchestrator"
    session_service = AsyncMock()

    async def fake_run(**_):
        yield _event(text="partial")
        raise RuntimeError("stream aborted")

    with patch("gclaw.dispatch.runner.Runner") as MockRunner:
        MockRunner.return_value.run_async = fake_run
        runner = AgentRunner(
            agent=agent,
            app_name="gclaw",
            session_service=session_service,
        )
        with pytest.raises(RuntimeError):
            await runner.run(user_id="u1", session_id="s1", message="hi")

    from opentelemetry.trace.status import StatusCode

    spans = [s for s in captured_spans.get_finished_spans()
             if s.name == "agent.orchestrator"]
    assert spans, "expected at least one agent span on failure"
    span = spans[-1]
    assert span.status.status_code == StatusCode.ERROR
    # The span carries the exception description verbatim.
    assert "stream aborted" in (span.status.description or "")


@pytest.mark.asyncio
async def test_run_uses_explicit_agent_name_for_span(captured_spans):
    """When the caller passes agent_name, the span uses that, not
    self._agent.name — this is the leaf-runner case where the chat API
    targets a specific agent on a shared runner."""
    agent = MagicMock()
    agent.name = "orchestrator"
    session_service = AsyncMock()

    async def fake_run(**_):
        yield _event(final=True)

    with patch("gclaw.dispatch.runner.Runner") as MockRunner:
        MockRunner.return_value.run_async = fake_run
        runner = AgentRunner(
            agent=agent,
            app_name="gclaw",
            session_service=session_service,
        )
        await runner.run(
            user_id="u1",
            session_id="s1",
            message="hi",
            agent_name="dev-mgr",
        )

    names = {s.name for s in captured_spans.get_finished_spans()}
    assert "agent.dev-mgr" in names
