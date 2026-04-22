"""Home manager tool stubs — pending smart home API integration spec."""

from __future__ import annotations

import logging

from gclaw.tools.catalog.builtin_registry import tool_export

logger = logging.getLogger(__name__)


@tool_export(description="List smart home devices (stub — not yet implemented).")
async def list_devices() -> str:
    """List smart home devices."""
    logger.info("list_devices stub called")
    return (
        "[list_devices is a stub placeholder]\n"
        "Smart home integration is not yet implemented. "
        "Follow-up spec will wire this up."
    )


@tool_export(description="Set the state of a smart home device (stub — not yet implemented).")
async def set_device_state(device_id: str, state: str) -> str:
    """Set the state of a smart home device."""
    logger.info("set_device_state stub: %s -> %s", device_id, state)
    return (
        f"[set_device_state is a stub placeholder: {device_id} -> {state}]\n"
        "Smart home integration is not yet implemented."
    )
