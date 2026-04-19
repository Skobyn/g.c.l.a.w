"""Tests for the local code-exec subprocess runner."""

from __future__ import annotations

import pytest

from gclaw.tools.catalog.models import CodeExecConfig
from gclaw.tools.code_exec.local_runner import LocalRunner


@pytest.fixture
def runner():
    return LocalRunner()


@pytest.mark.asyncio
async def test_python_stdout_captured(runner):
    out = await runner.execute(
        code="print('hello world')",
        config=CodeExecConfig(runtime="python3.12", timeout_seconds=5),
    )
    assert out["exit_code"] == 0
    assert out["stdout"].strip() == "hello world"
    assert out["stderr"] == ""
    assert out["truncated"] is False


@pytest.mark.asyncio
async def test_bash_runtime_supported(runner):
    out = await runner.execute(
        code="echo hi",
        config=CodeExecConfig(runtime="bash", timeout_seconds=5),
    )
    assert out["exit_code"] == 0
    assert "hi" in out["stdout"]


@pytest.mark.asyncio
async def test_exit_code_on_failure(runner):
    out = await runner.execute(
        code="raise SystemExit(7)",
        config=CodeExecConfig(runtime="python3.12", timeout_seconds=5),
    )
    assert out["exit_code"] == 7


@pytest.mark.asyncio
async def test_timeout_kills_process(runner):
    out = await runner.execute(
        code="import time; time.sleep(10)",
        config=CodeExecConfig(runtime="python3.12", timeout_seconds=1),
    )
    assert out["exit_code"] != 0
    assert "timeout" in (out.get("error") or out["stderr"]).lower()


@pytest.mark.asyncio
async def test_network_import_refused_by_policy(runner):
    out = await runner.execute(
        code="import socket\ns = socket.socket()",
        config=CodeExecConfig(
            runtime="python3.12", network="none", timeout_seconds=5
        ),
    )
    assert out["exit_code"] != 0
    assert (out.get("error") or "").lower().startswith("policy") or (
        "socket" in (out.get("error") or "").lower()
    )


@pytest.mark.asyncio
async def test_policy_bypassed_when_network_egress_only(runner):
    out = await runner.execute(
        code="import socket; print('ok')",
        config=CodeExecConfig(
            runtime="python3.12", network="egress-only", timeout_seconds=5
        ),
    )
    assert out["exit_code"] == 0
    assert "ok" in out["stdout"]


@pytest.mark.asyncio
async def test_stdout_truncation(runner):
    # 200 KB of output — should cap and flag truncation.
    code = "print('x' * 200_000)"
    out = await runner.execute(
        code=code,
        config=CodeExecConfig(runtime="python3.12", timeout_seconds=5),
    )
    assert out["truncated"] is True
    # Cap leaves head+tail under ~6 KB combined (3 KB + 3 KB by default).
    assert len(out["stdout"]) < 10_000


@pytest.mark.asyncio
async def test_duration_reported(runner):
    out = await runner.execute(
        code="print(1)",
        config=CodeExecConfig(runtime="python3.12", timeout_seconds=5),
    )
    assert "duration_ms" in out
    assert out["duration_ms"] >= 0
