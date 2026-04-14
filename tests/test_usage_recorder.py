"""UsageRecorder invariants — never-raises, disabled no-ops, delegates to repo."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from gclaw.models.usage import UsageKind
from gclaw.usage.recorder import (
    UsageRecorder,
    get_recorder,
    set_recorder,
    timed_record,
)


@pytest.fixture
def repo():
    return MagicMock()


@pytest.fixture
def recorder(repo):
    return UsageRecorder(repo=repo, enabled=True)


def test_record_model_call_delegates(recorder, repo):
    recorder.record_model_call(
        model_id="gemini-2.5-flash",
        provider_id="google_gemini",
        tokens_in=10,
        tokens_out=20,
        cost_usd=0.001,
        duration_ms=42,
    )
    assert repo.record.call_count == 1
    event = repo.record.call_args[0][0]
    assert event.kind == UsageKind.MODEL
    assert event.name == "gemini-2.5-flash"
    assert event.tokens_in == 10
    assert event.tokens_out == 20


def test_record_agent_invoke(recorder, repo):
    recorder.record_agent_invoke(agent_name="dev-mgr", caller="orchestrator")
    event = repo.record.call_args[0][0]
    assert event.kind == UsageKind.AGENT
    assert event.name == "dev-mgr"
    assert event.caller == "orchestrator"


def test_record_skill_use(recorder, repo):
    recorder.record_skill_use(skill_name="email-drafter", agent_name="workspace-mgr")
    event = repo.record.call_args[0][0]
    assert event.kind == UsageKind.SKILL
    assert event.caller == "workspace-mgr"


def test_record_tool_call(recorder, repo):
    recorder.record_tool_call(tool_name="create_board_task", agent_name="orchestrator")
    event = repo.record.call_args[0][0]
    assert event.kind == UsageKind.TOOL
    assert event.caller == "orchestrator"


def test_disabled_recorder_noops():
    repo = MagicMock()
    r = UsageRecorder(repo=repo, enabled=False)
    r.record_model_call(model_id="m")
    r.record_agent_invoke(agent_name="a")
    r.record_skill_use(skill_name="s")
    r.record_tool_call(tool_name="t")
    repo.record.assert_not_called()


def test_recorder_never_raises_when_repo_throws():
    repo = MagicMock()
    repo.record.side_effect = RuntimeError("firestore is down")
    r = UsageRecorder(repo=repo, enabled=True)
    # None of these should raise
    r.record_model_call(model_id="m")
    r.record_agent_invoke(agent_name="a")
    r.record_skill_use(skill_name="s")
    r.record_tool_call(tool_name="t")


def test_none_repo_means_disabled():
    r = UsageRecorder(repo=None, enabled=True)
    assert r.enabled is False
    r.record_agent_invoke(agent_name="a")  # must not raise


def test_module_singleton(repo):
    r = UsageRecorder(repo=repo, enabled=True)
    set_recorder(r)
    assert get_recorder() is r
    set_recorder(None)
    # Falls back to a no-op when not configured
    fallback = get_recorder()
    assert fallback.enabled is False


def test_timed_record_success(repo, recorder):
    with timed_record(
        recorder.record_tool_call,
        tool_name="x",
        agent_name="y",
    ) as ctx:
        ctx["metadata"]["result_size"] = 42
    assert repo.record.call_count == 1
    event = repo.record.call_args[0][0]
    assert event.kind == UsageKind.TOOL
    assert event.success is True
    assert event.metadata["result_size"] == 42


def test_timed_record_failure(repo, recorder):
    with pytest.raises(ValueError):
        with timed_record(
            recorder.record_tool_call,
            tool_name="x",
            agent_name="y",
        ):
            raise ValueError("boom")
    event = repo.record.call_args[0][0]
    assert event.success is False
    assert "boom" in (event.error or "")
