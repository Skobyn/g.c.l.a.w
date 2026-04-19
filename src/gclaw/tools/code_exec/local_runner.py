"""Local subprocess code-exec runner.

Best-effort sandbox — uses POSIX resource limits (memory cap via
RLIMIT_AS) and a strict timeout to contain runaway processes. Spawn
uses ``asyncio.create_subprocess_exec`` with an explicit argv list
(shell=False semantics) so there is no shell-expansion surface for
the agent-supplied code: the code is fed over stdin, never composed
into the command line.

NOT a true sandbox — determined attackers can bypass the AST policy
scan. Production runs should point ``TOOL_CODE_EXEC_REMOTE_URL`` at
the ``gclaw-sandbox`` Cloud Run service; see remote_runner.py.
"""

from __future__ import annotations

import asyncio
import logging
import resource
import shutil
import sys
import time
from typing import Any

from gclaw.tools.code_exec.policy import (
    NetworkPolicyViolation,
    check_python_source,
)

logger = logging.getLogger(__name__)

_STDOUT_CAP_BYTES = 3 * 1024
_MEMORY_BYTES_DEFAULT = 256 * 1024 * 1024


class LocalRunner:
    async def execute(self, *, code: str, config: Any) -> dict:
        start = time.perf_counter()
        runtime = getattr(config, "runtime", "python3.12")
        timeout = int(getattr(config, "timeout_seconds", 30) or 30)
        memory_mb = int(getattr(config, "memory_mb", 256) or 256)
        network = getattr(config, "network", "none")
        allowed_modules = getattr(config, "allowed_modules", []) or []

        if runtime.startswith("python"):
            try:
                check_python_source(
                    code, network=network, allowed_modules=allowed_modules
                )
            except NetworkPolicyViolation as e:
                duration_ms = int((time.perf_counter() - start) * 1000)
                return _fail(
                    error=f"policy violation: {e}", duration_ms=duration_ms
                )

        command = _command_for_runtime(runtime)
        if command is None:
            duration_ms = int((time.perf_counter() - start) * 1000)
            return _fail(
                error=f"runtime {runtime!r} unavailable on this host",
                duration_ms=duration_ms,
            )

        preexec = _build_preexec(memory_bytes=memory_mb * 1024 * 1024)
        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                preexec_fn=preexec,
            )
        except Exception as e:
            duration_ms = int((time.perf_counter() - start) * 1000)
            return _fail(
                error=f"subprocess launch failed: {e}",
                duration_ms=duration_ms,
            )

        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(input=code.encode("utf-8")), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            try:
                await proc.wait()
            except Exception:
                pass
            duration_ms = int((time.perf_counter() - start) * 1000)
            return _fail(
                error=f"timeout after {timeout}s",
                duration_ms=duration_ms,
                exit_code=-9,
            )

        duration_ms = int((time.perf_counter() - start) * 1000)
        stdout_text, truncated = _truncate(stdout_b.decode("utf-8", errors="replace"))
        stderr_text, _ = _truncate(stderr_b.decode("utf-8", errors="replace"))
        return {
            "stdout": stdout_text,
            "stderr": stderr_text,
            "exit_code": proc.returncode if proc.returncode is not None else -1,
            "duration_ms": duration_ms,
            "truncated": truncated,
        }


def _command_for_runtime(runtime: str) -> list[str] | None:
    if runtime.startswith("python"):
        # Matches the current interpreter. Version-specific pinning
        # (3.12 vs 3.13 etc.) is deferred to the remote runner.
        return [sys.executable, "-"]
    if runtime == "bash":
        bash_path = shutil.which("bash")
        if not bash_path:
            return None
        return [bash_path, "-s"]
    return None


def _build_preexec(*, memory_bytes: int):
    def _preexec() -> None:
        try:
            resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
        except Exception:
            pass

    return _preexec


def _truncate(text: str) -> tuple[str, bool]:
    cap = _STDOUT_CAP_BYTES * 2
    if len(text) <= cap:
        return text, False
    head = text[:_STDOUT_CAP_BYTES]
    tail = text[-_STDOUT_CAP_BYTES:]
    return f"{head}\n… (truncated from {len(text)} chars)\n{tail}", True


def _fail(*, error: str, duration_ms: int, exit_code: int = 1) -> dict:
    return {
        "stdout": "",
        "stderr": "",
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "truncated": False,
        "error": error,
    }
