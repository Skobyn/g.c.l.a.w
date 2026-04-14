"""Cron delivery dispatch — announce + webhook side-effects.

Separated from ``CronService`` so transports (Google Chat, Slack, etc.) can
evolve independently. A registry of named transports lets each cron pick
its own — with the env-configured default used when no name is supplied.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

import httpx

from gclaw.models.cron import (
    Cron,
    DeliveryAnnounce,
    DeliveryNone,
    DeliveryWebhook,
)

logger = logging.getLogger(__name__)


class AnnounceTransport(Protocol):
    """Pluggable announce sink. Returns True on success."""

    async def send(
        self,
        *,
        channel: str | None,
        to: str | None,
        account_id: str | None,
        message: str,
    ) -> bool:  # pragma: no cover - protocol definition
        ...


class LoggingAnnounceTransport:
    """Default transport — logs the message.

    Used until real channel adapters (Google Chat, Slack, SMS) are bound
    at composition time.
    """

    async def send(
        self,
        *,
        channel: str | None,
        to: str | None,
        account_id: str | None,
        message: str,
    ) -> bool:
        logger.info(
            "ANNOUNCE channel=%s to=%s account=%s msg=%r",
            channel,
            to,
            account_id,
            message[:200],
        )
        return True


class GoogleChatAnnounceTransport:
    """Announce via Google Chat using gws CLI (post_chat_message).

    ``channel`` is interpreted as the Chat space name (e.g.
    ``spaces/AAAA...``). ``to`` and ``account_id`` are ignored for now
    (single-account model).

    Degrades gracefully: ``post_chat_message`` surfaces gws CLI failures
    as strings that start with ``"Comms ... failed:"`` rather than
    raising, so environments without the gws CLI (dev machines) return
    ``False`` instead of exploding.
    """

    async def send(
        self,
        *,
        channel: str | None,
        to: str | None,
        account_id: str | None,
        message: str,
    ) -> bool:
        if not channel:
            logger.warning(
                "GoogleChatAnnounceTransport: no channel/space — "
                "dropping message"
            )
            return False
        from gclaw.tools.comms_tools import post_chat_message

        result = await post_chat_message(channel, message)
        lowered = result.lower()
        if lowered.startswith("comms ") and "failed" in lowered:
            logger.warning(
                "GoogleChatAnnounceTransport send failed: %s", result
            )
            return False
        return True


def build_transport_registry(
    settings: Any,
) -> tuple[dict[str, AnnounceTransport], str]:
    """Build the announce transport registry from settings.

    The registry always contains ``"logging"`` as the ultimate fallback.
    Extra transports are registered conditionally. The configured
    default (``settings.cron_announce_backend``) must be a known key;
    otherwise the default falls back to ``"logging"`` with a warning.

    Returns ``(registry, default_name)``.
    """
    registry: dict[str, AnnounceTransport] = {
        "logging": LoggingAnnounceTransport(),
        # GoogleChat construction is cheap — gws CLI failures only
        # surface when send() is actually invoked.
        "google_chat": GoogleChatAnnounceTransport(),
        # Future transports slot in here, e.g.:
        #   "slack": SlackAnnounceTransport(webhook_url=settings.slack_webhook),
        #   "discord": DiscordAnnounceTransport(token=settings.discord_token),
    }
    configured = getattr(settings, "cron_announce_backend", "logging")
    if configured in registry:
        default_name = configured
    else:
        logger.warning(
            "unknown announce backend %r — using logging", configured
        )
        default_name = "logging"
    return registry, default_name


def build_announce_transport(backend: str) -> AnnounceTransport:
    """Deprecated single-transport factory — kept for back-compat.

    Prefer :func:`build_transport_registry` for new code. This thin
    shim maps the old backend string onto the registry's pick so
    external callers don't break.
    """
    if backend == "google_chat":
        return GoogleChatAnnounceTransport()
    if backend == "logging":
        return LoggingAnnounceTransport()
    logger.warning(
        "unknown announce backend %r — using logging", backend
    )
    return LoggingAnnounceTransport()


class CronDeliveryService:
    """Dispatches cron success/failure messages via configured delivery.

    Accepts a registry of named announce transports; each cron picks
    one by name via ``DeliveryAnnounce.transport`` /
    ``FailureAlert.transport``. ``"default"`` (or unknown) resolves to
    the configured default transport.
    """

    def __init__(
        self,
        *,
        transports: dict[str, AnnounceTransport] | None = None,
        default_transport: str = "logging",
        announce_transport: AnnounceTransport | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        # Back-compat: legacy callers pass a single ``announce_transport``.
        # Wrap it as a one-entry registry under ``default_transport``.
        if transports is None:
            t = announce_transport or LoggingAnnounceTransport()
            transports = {
                "logging": LoggingAnnounceTransport(),
                default_transport: t,
            }
        # Always ensure "logging" is present as an ultimate fallback.
        transports.setdefault("logging", LoggingAnnounceTransport())
        self._transports = transports
        self._default = (
            default_transport
            if default_transport in transports
            else "logging"
        )
        self._http = http_client

    @property
    def default(self) -> str:
        """The configured default transport name."""
        return self._default

    def list_transports(self) -> list[str]:
        """Return all registered transport names, sorted."""
        return sorted(self._transports.keys())

    def _pick(self, name: str | None) -> AnnounceTransport:
        """Resolve a transport name. Unknown/default → configured default."""
        if not name or name == "default":
            return self._transports[self._default]
        picked = self._transports.get(name)
        if picked is None:
            logger.warning(
                "unknown cron announce transport %r — using default %r",
                name,
                self._default,
            )
            return self._transports[self._default]
        return picked

    # ---------------------------------------------------------------- success
    async def deliver_success(self, cron: Cron, *, summary: str) -> None:
        d = cron.delivery
        if isinstance(d, DeliveryNone):
            return

        if isinstance(d, DeliveryAnnounce):
            message = f"[cron:{cron.title}] {summary}"
            await self._safe_announce_raw(
                transport=self._pick(d.transport),
                channel=d.channel,
                to=d.to,
                account_id=d.account_id,
                message=message,
                best_effort=d.best_effort,
            )
            return

        if isinstance(d, DeliveryWebhook):
            payload: dict[str, Any] = {
                "event": "cron.success",
                "cron_id": cron.id,
                "title": cron.title,
                "summary": summary,
                "timestamp": (
                    cron.last_run.isoformat() if cron.last_run else None
                ),
            }
            await self._safe_webhook(
                d.url, payload, best_effort=d.best_effort
            )
            return

    # ---------------------------------------------------------------- failure
    async def deliver_failure_alert(
        self, cron: Cron, *, error: str
    ) -> bool:
        """Send a failure alert if threshold + cooldown allow.

        Returns True when an alert was dispatched (caller should persist
        ``last_alert_at = now()``). False when skipped for any reason.
        """
        fa = cron.failure_alert
        if fa is None:
            return False
        if cron.consecutive_errors < fa.after:
            return False

        now = datetime.now(timezone.utc)
        if cron.last_alert_at is not None:
            elapsed = now - cron.last_alert_at
            if elapsed < timedelta(milliseconds=fa.cooldown_ms):
                return False

        msg = (
            f"[cron-alert:{cron.title}] "
            f"failed {cron.consecutive_errors}x - {error[:300]}"
        )

        if fa.mode == "announce":
            await self._safe_announce_raw(
                transport=self._pick(fa.transport),
                channel=fa.channel,
                to=fa.to,
                account_id=None,
                message=msg,
                best_effort=True,
            )
            return True

        # mode == "webhook"
        if not fa.url:
            logger.warning(
                "failure_alert mode=webhook but no url set "
                "— skipping (cron=%s)",
                cron.id,
            )
            return False
        payload: dict[str, Any] = {
            "event": "cron.failure_alert",
            "cron_id": cron.id,
            "title": cron.title,
            "consecutive_errors": cron.consecutive_errors,
            "error": error,
            "timestamp": now.isoformat(),
        }
        await self._safe_webhook(fa.url, payload, best_effort=True)
        return True

    # -------------------------------------------------------------- internals
    async def _safe_announce_raw(
        self,
        *,
        transport: AnnounceTransport,
        channel: str | None,
        to: str | None,
        account_id: str | None,
        message: str,
        best_effort: bool,
    ) -> None:
        try:
            ok = await transport.send(
                channel=channel,
                to=to,
                account_id=account_id,
                message=message,
            )
            if not ok and not best_effort:
                raise RuntimeError("announce transport returned False")
        except Exception as e:
            if best_effort:
                logger.warning(
                    "announce failed (best_effort): %s", e
                )
            else:
                raise

    async def _safe_webhook(
        self, url: str, payload: dict, *, best_effort: bool
    ) -> None:
        try:
            client = self._http
            owns_client = client is None
            if client is None:
                client = httpx.AsyncClient(timeout=10.0)
            try:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
            finally:
                if owns_client:
                    await client.aclose()
        except Exception as e:
            if best_effort:
                logger.warning(
                    "webhook failed (best_effort) url=%s: %s", url, e
                )
            else:
                raise
