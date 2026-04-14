"""Round-trip UsageEvent of each kind through to_firestore_dict/from_firestore_dict."""

from __future__ import annotations

from datetime import datetime, timezone

from gclaw.models.usage import UsageEvent, UsageKind


def _roundtrip(event: UsageEvent) -> UsageEvent:
    data = event.to_firestore_dict()
    assert "id" not in data  # doc_id carries it separately
    return UsageEvent.from_firestore_dict(event.id, data)


def test_model_event_roundtrip():
    ev = UsageEvent(
        kind=UsageKind.MODEL,
        name="gemini-2.5-flash",
        provider_id="google_gemini",
        tokens_in=123,
        tokens_out=45,
        cost_usd=0.000123,
        duration_ms=321,
        user_id="u1",
        session_id="s1",
        caller="orchestrator",
    )
    back = _roundtrip(ev)
    assert back.kind == UsageKind.MODEL
    assert back.name == "gemini-2.5-flash"
    assert back.tokens_in == 123
    assert back.tokens_out == 45
    assert back.cost_usd == 0.000123
    assert back.id == ev.id


def test_agent_event_roundtrip():
    ev = UsageEvent(
        kind=UsageKind.AGENT,
        name="dev-mgr",
        caller="orchestrator",
        duration_ms=900,
        success=False,
        error="boom",
        metadata={"tool_call_count": 2},
    )
    back = _roundtrip(ev)
    assert back.kind == UsageKind.AGENT
    assert back.caller == "orchestrator"
    assert back.success is False
    assert back.error == "boom"
    assert back.metadata == {"tool_call_count": 2}


def test_skill_event_roundtrip():
    ev = UsageEvent(
        kind=UsageKind.SKILL,
        name="email-drafter",
        caller="workspace-mgr",
    )
    back = _roundtrip(ev)
    assert back.kind == UsageKind.SKILL
    assert back.name == "email-drafter"
    assert back.caller == "workspace-mgr"


def test_tool_event_roundtrip():
    ev = UsageEvent(
        kind=UsageKind.TOOL,
        name="create_board_task",
        caller="orchestrator",
        duration_ms=50,
        metadata={"args_keys": ["title", "assignee"]},
    )
    back = _roundtrip(ev)
    assert back.kind == UsageKind.TOOL
    assert back.caller == "orchestrator"
    assert back.metadata["args_keys"] == ["title", "assignee"]


def test_timestamp_default_is_utc_aware():
    ev = UsageEvent(kind=UsageKind.AGENT, name="x")
    assert ev.timestamp.tzinfo is not None
    # Default is recent
    assert (datetime.now(timezone.utc) - ev.timestamp).total_seconds() < 5
