"""AgentRunner + GuardrailService integration — end-to-end span attrs.

Confirms that:
  * A guardrail service wired into the runner actually gets called.
  * BLOCK outcome raises ``GuardrailBlockedError``.
  * guardrail.outcome + guardrail.violations land on the turn span.
  * A disabled service is a complete no-op (zero extra work).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gclaw.dispatch.runner import AgentRunner
from gclaw.guardrails.models import GuardrailBlockedError
from gclaw.guardrails.service import (
    GuardrailProfile,
    GuardrailService,
)
from gclaw.guardrails.validators import PiiValidator, ToxicityValidator
from gclaw.guardrails.models import Outcome


def _event(text=None, final=False):
    ev = MagicMock()
    ev.is_final_response.return_value = final
    if text:
        part = MagicMock()
        part.text = text
        part.function_call = None
        ev.content = MagicMock()
        ev.content.parts = [part]
    else:
        ev.content = MagicMock()
        ev.content.parts = None
    ev.usage_metadata = None
    ev.model_version = "gemini-2.5-flash"
    return ev


@pytest.fixture
def captured_spans():
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
async def test_guardrail_pass_sets_span_outcome_and_returns_text(
    captured_spans,
):
    agent = MagicMock()
    agent.name = "orchestrator"

    service = GuardrailService(enabled=True, default_profile="loose")

    async def fake_run(**_):
        yield _event(text="the project is tracking well")
        yield _event(final=True)

    with patch("gclaw.dispatch.runner.Runner") as MockRunner:
        MockRunner.return_value.run_async = fake_run
        runner = AgentRunner(
            agent=agent,
            app_name="gclaw",
            session_service=AsyncMock(),
            guardrail_service=service,
        )
        resp = await runner.run(user_id="u1", session_id="s1", message="hi")

    assert "tracking well" in resp.text
    spans = [s for s in captured_spans.get_finished_spans()
             if s.name == "agent.orchestrator"]
    attrs = dict(spans[0].attributes or {})
    assert attrs.get("guardrail.outcome") == "pass"


@pytest.mark.asyncio
async def test_guardrail_block_raises_and_stamps_violations(captured_spans):
    agent = MagicMock()
    agent.name = "orchestrator"

    prof = GuardrailProfile(
        name="kill",
        validators=[ToxicityValidator(outcome_for_detect=Outcome.BLOCK)],
    )
    service = GuardrailService(
        enabled=True, default_profile="kill", profiles={"kill": prof}
    )

    async def fake_run(**_):
        yield _event(text="you should kill yourself")
        yield _event(final=True)

    with patch("gclaw.dispatch.runner.Runner") as MockRunner:
        MockRunner.return_value.run_async = fake_run
        runner = AgentRunner(
            agent=agent,
            app_name="gclaw",
            session_service=AsyncMock(),
            guardrail_service=service,
        )
        with pytest.raises(GuardrailBlockedError) as exc_info:
            await runner.run(user_id="u1", session_id="s1", message="hi")

    assert exc_info.value.result.outcome == Outcome.BLOCK

    spans = [s for s in captured_spans.get_finished_spans()
             if s.name == "agent.orchestrator"]
    attrs = dict(spans[-1].attributes or {})
    assert attrs.get("guardrail.outcome") == "block"
    assert "toxicity" in attrs.get("guardrail.violations", "")


@pytest.mark.asyncio
async def test_disabled_guardrail_is_noop(captured_spans):
    agent = MagicMock()
    agent.name = "orchestrator"

    service = GuardrailService(enabled=False)

    async def fake_run(**_):
        yield _event(text="call me at (555) 123-4567")
        yield _event(final=True)

    with patch("gclaw.dispatch.runner.Runner") as MockRunner:
        MockRunner.return_value.run_async = fake_run
        runner = AgentRunner(
            agent=agent,
            app_name="gclaw",
            session_service=AsyncMock(),
            guardrail_service=service,
        )
        resp = await runner.run(user_id="u1", session_id="s1", message="hi")

    assert "(555)" in resp.text
    spans = [s for s in captured_spans.get_finished_spans()
             if s.name == "agent.orchestrator"]
    attrs = dict(spans[-1].attributes or {})
    # Disabled path should never stamp a guardrail outcome.
    assert "guardrail.outcome" not in attrs


@pytest.mark.asyncio
async def test_no_guardrail_service_is_noop():
    agent = MagicMock()
    agent.name = "orchestrator"

    async def fake_run(**_):
        yield _event(text="anything")
        yield _event(final=True)

    with patch("gclaw.dispatch.runner.Runner") as MockRunner:
        MockRunner.return_value.run_async = fake_run
        runner = AgentRunner(
            agent=agent,
            app_name="gclaw",
            session_service=AsyncMock(),
        )
        resp = await runner.run(user_id="u1", session_id="s1", message="hi")
    assert resp.text == "anything"


# Keep the PiiValidator reference exported (used elsewhere).
_ = PiiValidator
