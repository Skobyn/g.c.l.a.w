"""Tests for home tool stubs."""

import pytest

from gclaw.tools import home_tools


@pytest.mark.asyncio
async def test_list_devices_stub():
    result = await home_tools.list_devices()
    assert "stub" in result.lower() or "not yet" in result.lower()


@pytest.mark.asyncio
async def test_set_device_state_stub():
    result = await home_tools.set_device_state(device_id="light-1", state="on")
    assert "stub" in result.lower() or "not yet" in result.lower()
    assert "light-1" in result
