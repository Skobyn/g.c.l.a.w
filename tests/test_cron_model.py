"""Tests for the Cron v2 model (tagged-union schedule/payload/delivery)."""

from datetime import datetime, timezone

from gclaw.models.cron import (
    AgentTurnPayload,
    AtSchedule,
    Cron,
    CronExprSchedule,
    CronMode,
    CronStatus,
    DeliveryAnnounce,
    DeliveryNone,
    DeliveryWebhook,
    EverySchedule,
    FailureAlert,
    SystemEventPayload,
)


def _minimal_cron(**overrides):
    base = dict(
        title="Morning briefing",
        assignee="workspace-mgr",
        schedule=CronExprSchedule(expr="0 8 * * *"),
        payload=AgentTurnPayload(message="Give me the briefing"),
    )
    base.update(overrides)
    return Cron(**base)


def test_create_minimal_cron_defaults():
    cron = _minimal_cron()
    assert cron.title == "Morning briefing"
    assert cron.assignee == "workspace-mgr"
    assert cron.mode == CronMode.TODO
    assert cron.enabled is True
    assert cron.status == CronStatus.ACTIVE
    assert cron.wake_mode == "now"
    assert cron.delete_after_run is False
    assert cron.consecutive_errors == 0
    assert cron.last_error is None
    assert cron.id.startswith("cron_")
    assert isinstance(cron.delivery, DeliveryNone)


def test_enabled_and_status_stay_in_sync():
    paused = _minimal_cron(status=CronStatus.PAUSED)
    assert paused.enabled is False

    disabled = _minimal_cron(enabled=False)
    assert disabled.status == CronStatus.PAUSED


# --- Schedule round-trips ---------------------------------------------------


def test_at_schedule_round_trip():
    when = datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc)
    cron = _minimal_cron(schedule=AtSchedule(at=when))
    d = cron.to_firestore_dict()
    assert d["schedule"]["kind"] == "at"
    back = Cron.from_firestore_dict("cron_1", d)
    assert isinstance(back.schedule, AtSchedule)
    assert back.schedule.at == when


def test_every_schedule_round_trip():
    cron = _minimal_cron(
        schedule=EverySchedule(every_ms=60_000, anchor_ms=123)
    )
    d = cron.to_firestore_dict()
    assert d["schedule"] == {"kind": "every", "every_ms": 60_000, "anchor_ms": 123}
    back = Cron.from_firestore_dict("cron_1", d)
    assert isinstance(back.schedule, EverySchedule)
    assert back.schedule.every_ms == 60_000
    assert back.schedule.anchor_ms == 123


def test_cron_expr_schedule_round_trip():
    cron = _minimal_cron(
        schedule=CronExprSchedule(expr="0 8 * * *", tz="America/New_York", stagger_ms=500)
    )
    d = cron.to_firestore_dict()
    assert d["schedule"]["kind"] == "cron"
    back = Cron.from_firestore_dict("cron_1", d)
    assert isinstance(back.schedule, CronExprSchedule)
    assert back.schedule.expr == "0 8 * * *"
    assert back.schedule.tz == "America/New_York"
    assert back.schedule.stagger_ms == 500


# --- Payload round-trips ----------------------------------------------------


def test_agent_turn_payload_round_trip():
    cron = _minimal_cron(
        payload=AgentTurnPayload(
            message="do the thing", model="gemini-flash", timeout_seconds=30, light_context=True
        )
    )
    d = cron.to_firestore_dict()
    assert d["payload"]["kind"] == "agent_turn"
    back = Cron.from_firestore_dict("cron_1", d)
    assert isinstance(back.payload, AgentTurnPayload)
    assert back.payload.message == "do the thing"
    assert back.payload.model == "gemini-flash"
    assert back.payload.timeout_seconds == 30
    assert back.payload.light_context is True


def test_system_event_payload_round_trip():
    cron = _minimal_cron(
        payload=SystemEventPayload(text="standup reminder"),
        wake_mode="next-heartbeat",
    )
    d = cron.to_firestore_dict()
    assert d["payload"] == {"kind": "system_event", "text": "standup reminder"}
    back = Cron.from_firestore_dict("cron_1", d)
    assert isinstance(back.payload, SystemEventPayload)
    assert back.payload.text == "standup reminder"
    assert back.wake_mode == "next-heartbeat"


# --- Delivery round-trips ---------------------------------------------------


def test_delivery_none_default():
    cron = _minimal_cron()
    d = cron.to_firestore_dict()
    assert d["delivery"] == {"mode": "none"}


def test_delivery_announce_round_trip():
    cron = _minimal_cron(
        delivery=DeliveryAnnounce(channel="#ops", to="sbens", best_effort=True)
    )
    d = cron.to_firestore_dict()
    assert d["delivery"]["mode"] == "announce"
    back = Cron.from_firestore_dict("cron_1", d)
    assert isinstance(back.delivery, DeliveryAnnounce)
    assert back.delivery.channel == "#ops"
    assert back.delivery.best_effort is True


def test_delivery_webhook_round_trip():
    cron = _minimal_cron(
        delivery=DeliveryWebhook(url="https://example.com/hook", best_effort=False)
    )
    d = cron.to_firestore_dict()
    back = Cron.from_firestore_dict("cron_1", d)
    assert isinstance(back.delivery, DeliveryWebhook)
    assert back.delivery.url == "https://example.com/hook"


def test_failure_alert_round_trip():
    cron = _minimal_cron(
        failure_alert=FailureAlert(after=5, cooldown_ms=10_000, channel="#alerts")
    )
    d = cron.to_firestore_dict()
    back = Cron.from_firestore_dict("cron_1", d)
    assert back.failure_alert is not None
    assert back.failure_alert.after == 5
    assert back.failure_alert.channel == "#alerts"
    assert back.failure_alert.url is None


def test_failure_alert_webhook_url_round_trip():
    cron = _minimal_cron(
        failure_alert=FailureAlert(
            after=2,
            cooldown_ms=5_000,
            mode="webhook",
            url="https://example.com/alert",
        )
    )
    d = cron.to_firestore_dict()
    assert d["failure_alert"]["url"] == "https://example.com/alert"
    assert d["failure_alert"]["mode"] == "webhook"
    back = Cron.from_firestore_dict("cron_1", d)
    assert back.failure_alert is not None
    assert back.failure_alert.mode == "webhook"
    assert back.failure_alert.url == "https://example.com/alert"


def test_delivery_announce_transport_round_trip():
    cron = _minimal_cron(
        delivery=DeliveryAnnounce(transport="google_chat", channel="s"),
    )
    d = cron.to_firestore_dict()
    assert d["delivery"]["transport"] == "google_chat"
    back = Cron.from_firestore_dict("cron_1", d)
    assert isinstance(back.delivery, DeliveryAnnounce)
    assert back.delivery.transport == "google_chat"


def test_delivery_announce_legacy_dict_without_transport():
    # Legacy docs persisted before `transport` was added should deserialize
    # with the default sentinel.
    legacy = {"mode": "announce", "channel": "#ops"}
    d = DeliveryAnnounce(**legacy)
    assert d.transport == "default"


def test_failure_alert_transport_round_trip():
    cron = _minimal_cron(
        failure_alert=FailureAlert(
            after=2, cooldown_ms=0, transport="google_chat"
        ),
    )
    d = cron.to_firestore_dict()
    assert d["failure_alert"]["transport"] == "google_chat"
    back = Cron.from_firestore_dict("cron_1", d)
    assert back.failure_alert is not None
    assert back.failure_alert.transport == "google_chat"


def test_failure_alert_legacy_dict_without_transport():
    legacy = {"after": 3, "cooldown_ms": 1000, "mode": "announce"}
    fa = FailureAlert(**legacy)
    assert fa.transport == "default"


def test_failure_alert_legacy_dict_without_url_deserializes():
    # Ensure dicts persisted before the url field existed still load.
    legacy = {
        "after": 3,
        "cooldown_ms": 1000,
        "channel": "#alerts",
        "to": None,
        "mode": "announce",
    }
    fa = FailureAlert(**legacy)
    assert fa.url is None
    assert fa.channel == "#alerts"


# --- Backward compatibility -------------------------------------------------


def test_from_firestore_legacy_flat_shape_auto():
    now = datetime.now(timezone.utc)
    legacy = {
        "title": "Legacy AUTO cron",
        "description": "",
        "schedule": "0 8 * * MON",
        "mode": "auto",
        "status": "active",
        "assignee": "workspace-mgr",
        "task_priority": "medium",
        "last_run": None,
        "next_run": None,
        "created_at": now,
        "updated_at": now,
    }
    cron = Cron.from_firestore_dict("cron_legacy", legacy)
    assert cron.id == "cron_legacy"
    assert isinstance(cron.schedule, CronExprSchedule)
    assert cron.schedule.expr == "0 8 * * MON"
    assert isinstance(cron.payload, AgentTurnPayload)
    assert cron.payload.message == "Legacy AUTO cron"
    assert isinstance(cron.delivery, DeliveryNone)
    assert cron.wake_mode == "now"


def test_from_firestore_legacy_flat_shape_todo():
    now = datetime.now(timezone.utc)
    legacy = {
        "title": "Legacy TODO",
        "description": "pick me up later",
        "schedule": "0 9 * * *",
        "mode": "todo",
        "status": "active",
        "assignee": "dev-mgr",
        "task_priority": "low",
        "created_at": now,
        "updated_at": now,
    }
    cron = Cron.from_firestore_dict("cron_t", legacy)
    assert isinstance(cron.schedule, CronExprSchedule)
    assert cron.schedule.expr == "0 9 * * *"
    assert isinstance(cron.payload, AgentTurnPayload)
    assert cron.mode == CronMode.TODO


# --- Bookkeeping helpers ----------------------------------------------------


def test_record_run_resets_errors():
    cron = _minimal_cron(consecutive_errors=4, last_error="boom")
    updated = cron.record_run()
    assert updated.consecutive_errors == 0
    assert updated.last_error is None
    assert updated.last_run is not None


def test_record_failure_increments():
    cron = _minimal_cron()
    first = cron.record_failure("bad thing")
    assert first.consecutive_errors == 1
    assert first.last_error == "bad thing"
    second = first.record_failure("still bad")
    assert second.consecutive_errors == 2
