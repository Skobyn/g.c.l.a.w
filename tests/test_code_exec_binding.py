"""Tests wiring a CODE_EXEC catalog record through binding + tester."""

from __future__ import annotations

import pytest

from gclaw.tools.catalog.binding import ToolBindingService
from gclaw.tools.catalog.models import CodeExecConfig
from gclaw.tools.catalog.service import ToolCatalogService
from gclaw.tools.catalog.tester import probe_tool, set_code_exec_runner
from tests._tool_catalog_fakes import FakeToolRepo


class _FakeRunner:
    def __init__(self):
        self.calls = []

    async def execute(self, *, code, config):
        self.calls.append({"code": code, "config": config})
        return {
            "stdout": f"ran: {code.strip()}",
            "stderr": "",
            "exit_code": 0,
            "duration_ms": 1,
            "truncated": False,
        }


@pytest.fixture(autouse=True)
def _reset():
    set_code_exec_runner(None)
    yield
    set_code_exec_runner(None)


@pytest.fixture
def service():
    return ToolCatalogService(tool_repo=FakeToolRepo())


def test_binding_returns_callable(service):
    runner = _FakeRunner()
    rec = service.create_tool(
        name="sandbox",
        config=CodeExecConfig(runtime="python3.12"),
    )
    binding = ToolBindingService(
        catalog_service=service,
        code_exec_runner=runner,
    )
    tools = binding.resolve_catalog_tools([rec.id])
    assert len(tools) == 1
    assert callable(tools[0])


@pytest.mark.asyncio
async def test_bound_callable_executes(service):
    runner = _FakeRunner()
    rec = service.create_tool(
        name="sandbox",
        config=CodeExecConfig(runtime="python3.12"),
    )
    binding = ToolBindingService(
        catalog_service=service,
        code_exec_runner=runner,
    )
    tool = binding.resolve_catalog_tools([rec.id])[0]
    out = await tool(code="print('x')")
    assert "ran:" in out
    assert runner.calls[0]["code"] == "print('x')"
    assert runner.calls[0]["config"].runtime == "python3.12"


def test_binding_without_runner_is_silent_skip(service):
    rec = service.create_tool(
        name="sandbox",
        config=CodeExecConfig(runtime="python3.12"),
    )
    binding = ToolBindingService(
        catalog_service=service,
        code_exec_runner=None,
    )
    assert binding.resolve_catalog_tools([rec.id]) == []


@pytest.mark.asyncio
async def test_tester_code_exec_probes_with_ok_payload(service):
    runner = _FakeRunner()
    set_code_exec_runner(runner)
    rec = service.create_tool(
        name="sandbox",
        config=CodeExecConfig(runtime="python3.12"),
    )
    result = await probe_tool(rec)
    assert result["ok"] is True
    assert "ran:" in result["sample_response"]["stdout"]


@pytest.mark.asyncio
async def test_tester_code_exec_without_runner_is_stub(service):
    rec = service.create_tool(
        name="sandbox",
        config=CodeExecConfig(runtime="python3.12"),
    )
    result = await probe_tool(rec)
    assert result["ok"] is False
    assert "phase" in result["error"].lower()
