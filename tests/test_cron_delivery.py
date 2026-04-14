"""Tests for CronDeliveryService — announce + webhook side-effects."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import httpx
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
    DeliveryNone,
    DeliveryWebhook,
    FailureAlert,
)


def _make_cron(**overrides):
    base = dict(
        id="cron_1",
        title="MyCron",
        assignee="workspace-mgr",
        schedule=CronExprSchedule(expr="0 8 * * *"),
        payload=AgentTurnPayload(message="do it"),
    )
    base.update(overrides)
    return Cron(**base)


# --------------------------------------------------------------- deliver_success


async def test_deliver_success_mode_none_does_nothing():
    transport = MagicMock()
    transport.send = AsyncMock(return_value=True)
    svc = CronDeliveryService(announce_transport=transport)
    cron = _make_cron(delivery=DeliveryNone())

    await svc.deliver_success(cron, summary="ok")

    transport.send.assert_not_called()


async def test_deliver_success_announce_calls_transport():
    transport = MagicMock()
    transport.send = AsyncMock(return_value=True)
    svc = CronDeliveryService(announce_transport=transport)
    cron = _make_cron(
        delivery=DeliveryAnnounce(
            channel="spaces/ABC", to=None, account_id="gws"
        )
    )

    await svc.deliver_success(cron, summary="task_123 created")

    transport.send.assert_awaited_once()
    kw = transport.send.call_args.kwargs
    assert kw["channel"] == "spaces/ABC"
    assert kw["account_id"] == "gws"
    assert "MyCron" in kw["message"]
    assert "task_123 created" in kw["message"]


async def test_deliver_success_webhook_posts_payload():
    captured: dict = {}

    async def _handler(request: httpx.Request) -> httpx.Response:
        import json as _json
        captured["url"] = str(request.url)
        captured["body"] = _json.loads(request.content)
        return httpx.Response(200)

    http = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
    try:
        svc = CronDeliveryService(http_client=http)
        cron = _make_cron(
            delivery=DeliveryWebhook(url="https://example.com/hook"),
            last_run=datetime(2026, 4, 14, 8, 0, tzinfo=timezone.utc),
        )
        await svc.deliver_success(cron, summary="task_abc created")
    finally:
        await http.aclose()

    assert captured["url"] == "https://example.com/hook"
    body = captured["body"]
    assert body["event"] == "cron.success"
    assert body["cron_id"] == "cron_1"
    assert body["title"] == "MyCron"
    assert body["summary"] == "task_abc created"
    assert body["timestamp"] == "2026-04-14T08:00:00+00:00"


# ---------------------------------------------------------- deliver_failure_alert


async def test_failure_alert_skipped_below_threshold():
    transport = MagicMock()
    transport.send = AsyncMock(return_value=True)
    svc = CronDeliveryService(announce_transport=transport)

    cron = _make_cron(
        failure_alert=FailureAlert(after=3, cooldown_ms=0),
        consecutive_errors=2,
    )
    sent = await svc.deliver_failure_alert(cron, error="boom")

    assert sent is False
    transport.send.assert_not_called()


async def test_failure_alert_skipped_during_cooldown():
    transport = MagicMock()
    transport.send = AsyncMock(return_value=True)
    svc = CronDeliveryService(announce_transport=transport)

    recent = datetime.now(timezone.utc) - timedelta(seconds=30)
    cron = _make_cron(
        failure_alert=FailureAlert(after=1, cooldown_ms=3_600_000),
        consecutive_errors=5,
        last_alert_at=recent,
    )
    sent = await svc.deliver_failure_alert(cron, error="boom")

    assert sent is False
    transport.send.assert_not_called()


async def test_failure_alert_fires_when_threshold_met_no_cooldown():
    transport = MagicMock()
    transport.send = AsyncMock(return_value=True)
    svc = CronDeliveryService(announce_transport=transport)

    cron = _make_cron(
        failure_alert=FailureAlert(
            after=3, cooldown_ms=60_000, channel="ops", to=None, mode="announce"
        ),
        consecutive_errors=3,
        last_alert_at=None,
    )
    sent = await svc.deliver_failure_alert(cron, error="kaboom")

    assert sent is True
    transport.send.assert_awaited_once()
    kw = transport.send.call_args.kwargs
    assert kw["channel"] == "ops"
    assert "kaboom" in kw["message"]
    assert "3x" in kw["message"]


async def test_failure_alert_none_no_op():
    transport = MagicMock()
    transport.send = AsyncMock(return_value=True)
    svc = CronDeliveryService(announce_transport=transport)

    cron = _make_cron(failure_alert=None, consecutive_errors=99)
    sent = await svc.deliver_failure_alert(cron, error="nope")

    assert sent is False
    transport.send.assert_not_called()


async def test_failure_alert_webhook_mode_without_url_skips(caplog):
    """mode=webhook with no url — skip, don't bump cooldown."""
    import logging

    transport = MagicMock()
    transport.send = AsyncMock(return_value=True)

    posted: list = []

    async def _handler(request: httpx.Request) -> httpx.Response:
        posted.append(request)
        return httpx.Response(200)

    http = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
    try:
        svc = CronDeliveryService(
            announce_transport=transport, http_client=http
        )
        cron = _make_cron(
            failure_alert=FailureAlert(
                after=1, cooldown_ms=0, mode="webhook", url=None
            ),
            consecutive_errors=1,
        )
        with caplog.at_level(logging.WARNING, logger="gclaw.cron.delivery"):
            sent = await svc.deliver_failure_alert(cron, error="boom")
    finally:
        await http.aclose()

    assert sent is False  # no alert dispatched, caller should not bump cooldown
    transport.send.assert_not_called()
    assert posted == []
    assert any("no url set" in r.message for r in caplog.records)


async def test_failure_alert_webhook_mode_with_url_posts():
    """mode=webhook with url — real POST with full payload."""
    captured: dict = {}

    async def _handler(request: httpx.Request) -> httpx.Response:
        import json as _json
        captured["url"] = str(request.url)
        captured["body"] = _json.loads(request.content)
        return httpx.Response(200)

    http = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
    try:
        svc = CronDeliveryService(http_client=http)
        cron = _make_cron(
            failure_alert=FailureAlert(
                after=2,
                cooldown_ms=0,
                mode="webhook",
                url="https://example.com/hook",
            ),
            consecutive_errors=4,
        )
        sent = await svc.deliver_failure_alert(cron, error="kaboom")
    finally:
        await http.aclose()

    assert sent is True
    assert captured["url"] == "https://example.com/hook"
    body = captured["body"]
    assert body["event"] == "cron.failure_alert"
    assert body["cron_id"] == "cron_1"
    assert body["title"] == "MyCron"
    assert body["consecutive_errors"] == 4
    assert body["error"] == "kaboom"
    assert "timestamp" in body and body["timestamp"]


# ---------------------------------------------------------------- best_effort


async def test_best_effort_true_swallows_announce_errors():
    transport = MagicMock()
    transport.send = AsyncMock(side_effect=RuntimeError("network"))
    svc = CronDeliveryService(announce_transport=transport)

    cron = _make_cron(
        delivery=DeliveryAnnounce(channel="x", best_effort=True)
    )
    # Should not raise.
    await svc.deliver_success(cron, summary="s")


async def test_best_effort_false_reraises_announce_errors():
    transport = MagicMock()
    transport.send = AsyncMock(side_effect=RuntimeError("network"))
    svc = CronDeliveryService(announce_transport=transport)

    cron = _make_cron(
        delivery=DeliveryAnnounce(channel="x", best_effort=False)
    )
    with pytest.raises(RuntimeError, match="network"):
        await svc.deliver_success(cron, summary="s")


async def test_best_effort_true_swallows_webhook_errors():
    async def _boom(request):
        return httpx.Response(500)

    http = httpx.AsyncClient(transport=httpx.MockTransport(_boom))
    try:
        svc = CronDeliveryService(http_client=http)
        cron = _make_cron(
            delivery=DeliveryWebhook(
                url="https://example.com/hook", best_effort=True
            )
        )
        # Should not raise.
        await svc.deliver_success(cron, summary="s")
    finally:
        await http.aclose()


async def test_best_effort_false_reraises_webhook_errors():
    async def _boom(request):
        return httpx.Response(500)

    http = httpx.AsyncClient(transport=httpx.MockTransport(_boom))
    try:
        svc = CronDeliveryService(http_client=http)
        cron = _make_cron(
            delivery=DeliveryWebhook(
                url="https://example.com/hook", best_effort=False
            )
        )
        with pytest.raises(httpx.HTTPStatusError):
            await svc.deliver_success(cron, summary="s")
    finally:
        await http.aclose()


# ------------------------------------------------------------------ transport


async def test_logging_announce_transport_returns_true(caplog):
    t = LoggingAnnounceTransport()
    ok = await t.send(
        channel="c", to="t", account_id="a", message="hello"
    )
    assert ok is True
