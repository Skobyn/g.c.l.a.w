"""AgentRunner fallback chain: retry swap on retryable model errors."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.api_core import exceptions as gapi_exc

from gclaw.dispatch.runner import AgentRunner
from gclaw.usage.recorder import UsageRecorder


def _event(text=None, final=False, model_version=None):
    ev = MagicMock()
    ev.is_final_response.return_value = final
    if text:
        p = MagicMock()
        p.text = text
        p.function_call = None
        ev.content = MagicMock()
        ev.content.parts = [p]
    else:
        ev.content = MagicMock()
        ev.content.parts = None
    ev.usage_metadata = None
    ev.model_version = model_version
    return ev


def _install_runner_mock(runners: list):
    """Return a factory that yields the next pre-prepared runner each call."""
    call_count = {"n": 0}

    def factory(*args, **kwargs):
        idx = call_count["n"]
        call_count["n"] += 1
        return runners[idx]

    return factory


@pytest.mark.asyncio
async def test_primary_fails_fallback_succeeds():
    agent = MagicMock(spec_set=["name", "model"])
    agent.name = "orchestrator"
    agent.model = "primary-model"
    session_service = AsyncMock()
    repo = MagicMock()
    recorder = UsageRecorder(repo=repo, enabled=True)

    async def fail_stream(**kwargs):
        raise gapi_exc.ResourceExhausted("quota")
        yield  # pragma: no cover

    async def ok_stream(**kwargs):
        yield _event(text="recovered", final=True, model_version="fallback-1")

    primary_runner = MagicMock()
    primary_runner.run_async = fail_stream
    fallback_runner = MagicMock()
    fallback_runner.run_async = ok_stream

    chain = ["primary-model", "fallback-1", "fallback-2"]

    with patch(
        "gclaw.dispatch.runner.Runner",
        side_effect=_install_runner_mock([primary_runner, fallback_runner]),
    ):
        runner = AgentRunner(
            agent=agent,
            app_name="gclaw",
            session_service=session_service,
            usage_recorder=recorder,
            model_chain_provider=lambda name: chain,
        )
        resp = await runner.run(user_id="u1", session_id="s1", message="hi")

    assert resp.text == "recovered"
    # Expect two agent_invoke records: first failure, then success.
    agent_evs = [c.args[0] for c in repo.record.call_args_list
                 if c.args[0].kind.value == "agent"]
    assert len(agent_evs) == 2
    assert agent_evs[0].success is False
    assert agent_evs[1].success is True
    assert agent_evs[1].metadata.get("fallback_index") == 1


@pytest.mark.asyncio
async def test_all_fallbacks_exhaust_raises():
    agent = MagicMock(spec_set=["name", "model"])
    agent.name = "orchestrator"
    agent.model = "primary-model"
    session_service = AsyncMock()
    repo = MagicMock()
    recorder = UsageRecorder(repo=repo, enabled=True)

    async def fail_stream(**kwargs):
        raise gapi_exc.ServiceUnavailable("down")
        yield  # pragma: no cover

    r1 = MagicMock(); r1.run_async = fail_stream
    r2 = MagicMock(); r2.run_async = fail_stream
    r3 = MagicMock(); r3.run_async = fail_stream

    with patch(
        "gclaw.dispatch.runner.Runner",
        side_effect=_install_runner_mock([r1, r2, r3]),
    ):
        runner = AgentRunner(
            agent=agent,
            app_name="gclaw",
            session_service=session_service,
            usage_recorder=recorder,
            model_chain_provider=lambda name: ["p", "f1", "f2"],
        )
        with pytest.raises(gapi_exc.ServiceUnavailable):
            await runner.run(user_id="u1", session_id="s1", message="hi")

    agent_evs = [c.args[0] for c in repo.record.call_args_list
                 if c.args[0].kind.value == "agent"]
    assert len(agent_evs) == 3
    assert all(ev.success is False for ev in agent_evs)
    # fallback_index advances 0, 1, 2.
    indexes = [ev.metadata.get("fallback_index", 0) for ev in agent_evs]
    assert indexes == [0, 1, 2]


@pytest.mark.asyncio
async def test_non_retryable_exception_raises_immediately():
    agent = MagicMock(spec_set=["name", "model"])
    agent.name = "orchestrator"
    agent.model = "primary-model"
    session_service = AsyncMock()
    repo = MagicMock()
    recorder = UsageRecorder(repo=repo, enabled=True)

    async def fail_stream(**kwargs):
        raise ValueError("programming error")
        yield  # pragma: no cover

    primary_runner = MagicMock()
    primary_runner.run_async = fail_stream

    with patch(
        "gclaw.dispatch.runner.Runner",
        side_effect=_install_runner_mock([primary_runner]),
    ):
        runner = AgentRunner(
            agent=agent,
            app_name="gclaw",
            session_service=session_service,
            usage_recorder=recorder,
            model_chain_provider=lambda name: ["p", "f1"],
        )
        with pytest.raises(ValueError):
            await runner.run(user_id="u1", session_id="s1", message="hi")

    agent_evs = [c.args[0] for c in repo.record.call_args_list
                 if c.args[0].kind.value == "agent"]
    # Only one attempt recorded — no fallback retry for ValueError.
    assert len(agent_evs) == 1
    assert agent_evs[0].success is False


@pytest.mark.asyncio
async def test_no_chain_provider_primary_failure_raises():
    agent = MagicMock(spec_set=["name", "model"])
    agent.name = "orchestrator"
    agent.model = "primary-model"
    session_service = AsyncMock()
    repo = MagicMock()
    recorder = UsageRecorder(repo=repo, enabled=True)

    async def fail_stream(**kwargs):
        raise gapi_exc.ResourceExhausted("quota")
        yield  # pragma: no cover

    primary_runner = MagicMock()
    primary_runner.run_async = fail_stream

    with patch(
        "gclaw.dispatch.runner.Runner",
        side_effect=_install_runner_mock([primary_runner]),
    ):
        runner = AgentRunner(
            agent=agent,
            app_name="gclaw",
            session_service=session_service,
            usage_recorder=recorder,
            # no model_chain_provider
        )
        with pytest.raises(gapi_exc.ResourceExhausted):
            await runner.run(user_id="u1", session_id="s1", message="hi")

    agent_evs = [c.args[0] for c in repo.record.call_args_list
                 if c.args[0].kind.value == "agent"]
    assert len(agent_evs) == 1
    assert agent_evs[0].success is False


@pytest.mark.asyncio
async def test_empty_chain_primary_failure_raises():
    """model_chain_provider returns []; primary failure should not retry."""
    agent = MagicMock(spec_set=["name", "model"])
    agent.name = "orchestrator"
    agent.model = "primary-model"
    session_service = AsyncMock()
    repo = MagicMock()
    recorder = UsageRecorder(repo=repo, enabled=True)

    async def fail_stream(**kwargs):
        raise gapi_exc.DeadlineExceeded("slow")
        yield  # pragma: no cover

    primary_runner = MagicMock()
    primary_runner.run_async = fail_stream

    with patch(
        "gclaw.dispatch.runner.Runner",
        side_effect=_install_runner_mock([primary_runner]),
    ):
        runner = AgentRunner(
            agent=agent,
            app_name="gclaw",
            session_service=session_service,
            usage_recorder=recorder,
            model_chain_provider=lambda name: [],
        )
        with pytest.raises(gapi_exc.DeadlineExceeded):
            await runner.run(user_id="u1", session_id="s1", message="hi")

    agent_evs = [c.args[0] for c in repo.record.call_args_list
                 if c.args[0].kind.value == "agent"]
    assert len(agent_evs) == 1


@pytest.mark.asyncio
async def test_genai_client_error_429_is_retryable():
    """google.genai.errors.ClientError with 429 triggers fallback."""
    from google.genai import errors as genai_errors

    agent = MagicMock(spec_set=["name", "model"])
    agent.name = "orchestrator"
    agent.model = "primary-model"
    session_service = AsyncMock()
    repo = MagicMock()
    recorder = UsageRecorder(repo=repo, enabled=True)

    async def fail_stream(**kwargs):
        raise genai_errors.ClientError(
            429, {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED"}}
        )
        yield  # pragma: no cover

    async def ok_stream(**kwargs):
        yield _event(text="recovered", final=True, model_version="fallback-1")

    primary_runner = MagicMock()
    primary_runner.run_async = fail_stream
    fallback_runner = MagicMock()
    fallback_runner.run_async = ok_stream

    with patch(
        "gclaw.dispatch.runner.Runner",
        side_effect=_install_runner_mock([primary_runner, fallback_runner]),
    ):
        runner = AgentRunner(
            agent=agent,
            app_name="gclaw",
            session_service=session_service,
            usage_recorder=recorder,
            model_chain_provider=lambda name: ["primary-model", "fallback-1"],
        )
        resp = await runner.run(user_id="u1", session_id="s1", message="hi")

    assert resp.text == "recovered"


@pytest.mark.asyncio
async def test_genai_client_error_400_is_not_retryable():
    """A 400 INVALID_ARGUMENT is a programming error — no fallback."""
    from google.genai import errors as genai_errors

    agent = MagicMock(spec_set=["name", "model"])
    agent.name = "orchestrator"
    agent.model = "primary-model"
    session_service = AsyncMock()
    repo = MagicMock()
    recorder = UsageRecorder(repo=repo, enabled=True)

    async def fail_stream(**kwargs):
        raise genai_errors.ClientError(
            400, {"error": {"message": "bad", "status": "INVALID_ARGUMENT"}}
        )
        yield  # pragma: no cover

    primary_runner = MagicMock()
    primary_runner.run_async = fail_stream

    with patch(
        "gclaw.dispatch.runner.Runner",
        side_effect=_install_runner_mock([primary_runner]),
    ):
        runner = AgentRunner(
            agent=agent,
            app_name="gclaw",
            session_service=session_service,
            usage_recorder=recorder,
            model_chain_provider=lambda name: ["primary-model", "fallback-1"],
        )
        with pytest.raises(genai_errors.ClientError):
            await runner.run(user_id="u1", session_id="s1", message="hi")

    agent_evs = [c.args[0] for c in repo.record.call_args_list
                 if c.args[0].kind.value == "agent"]
    # Only one attempt — no fallback retry for non-retryable client error.
    assert len(agent_evs) == 1


@pytest.mark.asyncio
async def test_genai_server_error_is_retryable():
    """5xx from google.genai triggers fallback."""
    from google.genai import errors as genai_errors

    agent = MagicMock(spec_set=["name", "model"])
    agent.name = "orchestrator"
    agent.model = "primary-model"
    session_service = AsyncMock()
    repo = MagicMock()
    recorder = UsageRecorder(repo=repo, enabled=True)

    async def fail_stream(**kwargs):
        raise genai_errors.ServerError(
            503, {"error": {"message": "unavailable", "status": "UNAVAILABLE"}}
        )
        yield  # pragma: no cover

    async def ok_stream(**kwargs):
        yield _event(text="recovered", final=True, model_version="fallback-1")

    primary_runner = MagicMock()
    primary_runner.run_async = fail_stream
    fallback_runner = MagicMock()
    fallback_runner.run_async = ok_stream

    with patch(
        "gclaw.dispatch.runner.Runner",
        side_effect=_install_runner_mock([primary_runner, fallback_runner]),
    ):
        runner = AgentRunner(
            agent=agent,
            app_name="gclaw",
            session_service=session_service,
            usage_recorder=recorder,
            model_chain_provider=lambda name: ["primary-model", "fallback-1"],
        )
        resp = await runner.run(user_id="u1", session_id="s1", message="hi")

    assert resp.text == "recovered"


@pytest.mark.asyncio
async def test_primary_only_chain_no_fallbacks_raises():
    """Chain of length 1 means no fallbacks available."""
    agent = MagicMock(spec_set=["name", "model"])
    agent.name = "orchestrator"
    agent.model = "primary-model"
    session_service = AsyncMock()
    repo = MagicMock()
    recorder = UsageRecorder(repo=repo, enabled=True)

    async def fail_stream(**kwargs):
        raise gapi_exc.InternalServerError("boom")
        yield  # pragma: no cover

    primary_runner = MagicMock()
    primary_runner.run_async = fail_stream

    with patch(
        "gclaw.dispatch.runner.Runner",
        side_effect=_install_runner_mock([primary_runner]),
    ):
        runner = AgentRunner(
            agent=agent,
            app_name="gclaw",
            session_service=session_service,
            usage_recorder=recorder,
            model_chain_provider=lambda name: ["primary-model"],
        )
        with pytest.raises(gapi_exc.InternalServerError):
            await runner.run(user_id="u1", session_id="s1", message="hi")
