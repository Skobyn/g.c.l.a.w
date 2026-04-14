"""Tests for build_announce_transport factory."""

from __future__ import annotations

import logging

from gclaw.cron.delivery import (
    GoogleChatAnnounceTransport,
    LoggingAnnounceTransport,
    build_announce_transport,
)


def test_build_logging_transport():
    t = build_announce_transport("logging")
    assert isinstance(t, LoggingAnnounceTransport)


def test_build_google_chat_transport():
    t = build_announce_transport("google_chat")
    assert isinstance(t, GoogleChatAnnounceTransport)


def test_build_unknown_backend_falls_back_to_logging(caplog):
    with caplog.at_level(logging.WARNING, logger="gclaw.cron.delivery"):
        t = build_announce_transport("bogus")
    assert isinstance(t, LoggingAnnounceTransport)
    assert any(
        "unknown announce backend" in rec.message.lower()
        for rec in caplog.records
    )
