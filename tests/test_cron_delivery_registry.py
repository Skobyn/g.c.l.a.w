"""Tests for the per-cron transport registry in CronDeliveryService."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from gclaw.cron.delivery import (
    CronDeliveryService,
    LoggingAnnounceTransport,
)
from gclaw.models.cron import (
    AgentTurnPayload,
    Cron,
    CronExprSchedule,
    DeliveryAnnounce,
    FailureAlert,
)


def _make_cron(**overrides):
    base = dict(
        id="cron_1",
        title="T",
        assignee="workspace-mgr",
        schedule=CronExprSchedule(expr="0 8 * * *"),
        payload=AgentTurnPayload(message="go"),
    )
    base.update(overrides)
    return Cron(**base)


def _mk_transport():
    t = MagicMock()
    t.send = AsyncMock(return_value=True)
    return t


def test_pick_default_returns_default_transport():
    gc = _mk_transport()
    lg = _mk_transport()
    svc = CronDeliveryService(
        transports={"google_chat": gc, "logging": lg},
        default_transport="google_chat",
    )
    assert svc._pick("default") is gc
    assert svc._pick(None) is gc


def test_pick_named_returns_named_transport():
    gc = _mk_transport()
    lg = _mk_transport()
    svc = CronDeliveryService(
        transports={"google_chat": gc, "logging": lg},
        default_transport="google_chat",
    )
    assert svc._pick("logging") is lg


def test_pick_unknown_falls_back_to_default_with_warning(caplog):
    gc = _mk_transport()
    svc = CronDeliveryService(
        transports={"google_chat": gc},
        default_transport="google_chat",
    )
    with caplog.at_level(logging.WARNING, logger="gclaw.cron.delivery"):
        picked = svc._pick("bogus")
    assert picked is gc
    assert any(
        "unknown cron announce transport" in r.message.lower()
        for r in caplog.records
    )


def test_list_transports_includes_logging_and_is_sorted():
    gc = _mk_transport()
    svc = CronDeliveryService(
        transports={"google_chat": gc},
        default_transport="google_chat",
    )
    names = svc.list_transports()
    assert names == sorted(names)
    assert "logging" in names
    assert "google_chat" in names


def test_default_property_reflects_configured_default():
    gc = _mk_transport()
    svc = CronDeliveryService(
        transports={"google_chat": gc, "logging": LoggingAnnounceTransport()},
        default_transport="google_chat",
    )
    assert svc.default == "google_chat"


def test_unknown_default_falls_back_to_logging():
    svc = CronDeliveryService(
        transports={"logging": LoggingAnnounceTransport()},
        default_transport="nope",
    )
    assert svc.default == "logging"


@pytest.mark.asyncio
async def test_deliver_success_uses_named_transport_only():
    gc = _mk_transport()
    lg = _mk_transport()
    svc = CronDeliveryService(
        transports={"google_chat": gc, "logging": lg},
        default_transport="logging",
    )
    cron = _make_cron(
        delivery=DeliveryAnnounce(transport="google_chat", channel="s"),
    )
    await svc.deliver_success(cron, summary="ok")
    gc.send.assert_awaited_once()
    lg.send.assert_not_called()


@pytest.mark.asyncio
async def test_deliver_failure_alert_uses_its_own_transport():
    gc = _mk_transport()
    lg = _mk_transport()
    svc = CronDeliveryService(
        transports={"google_chat": gc, "logging": lg},
        default_transport="google_chat",
    )
    cron = _make_cron(
        failure_alert=FailureAlert(
            after=1, cooldown_ms=0, mode="announce", transport="logging",
            channel="ops",
        ),
        consecutive_errors=1,
    )
    sent = await svc.deliver_failure_alert(cron, error="boom")
    assert sent is True
    lg.send.assert_awaited_once()
    gc.send.assert_not_called()


def test_back_compat_single_announce_transport():
    t = _mk_transport()
    svc = CronDeliveryService(announce_transport=t, default_transport="custom")
    # single transport registered under the default name
    assert svc.default == "custom"
    assert "logging" in svc.list_transports()
    assert "custom" in svc.list_transports()
    assert svc._pick("default") is t


def test_build_transport_registry_returns_default_from_settings():
    from gclaw.cron.delivery import build_transport_registry

    class S:
        cron_announce_backend = "google_chat"

    registry, default = build_transport_registry(S())
    assert default == "google_chat"
    assert "logging" in registry
    assert "google_chat" in registry


def test_build_transport_registry_unknown_falls_back_to_logging(caplog):
    from gclaw.cron.delivery import build_transport_registry

    class S:
        cron_announce_backend = "bogus"

    with caplog.at_level(logging.WARNING, logger="gclaw.cron.delivery"):
        _, default = build_transport_registry(S())
    assert default == "logging"
    assert any(
        "unknown announce backend" in r.message.lower()
        for r in caplog.records
    )
