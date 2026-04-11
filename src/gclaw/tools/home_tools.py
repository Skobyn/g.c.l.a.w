"""Home manager tool stubs — pending smart home API integration spec."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def list_devices() -> str:
    """List smart home devices."""
    logger.info("list_devices stub called")
    return (
        "[list_devices is a stub placeholder]\n"
        "Smart home integration is not yet implemented. "
        "Follow-up spec will wire this up."
    )


async def set_device_state(device_id: str, state: str) -> str:
    """Set the state of a smart home device."""
    logger.info("set_device_state stub: %s -> %s", device_id, state)
    return (
        f"[set_device_state is a stub placeholder: {device_id} -> {state}]\n"
        "Smart home integration is not yet implemented."
    )
