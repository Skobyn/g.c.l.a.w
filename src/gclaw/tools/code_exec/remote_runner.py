"""Remote code-exec runner — proxies to a Cloud Run sibling service.

The sandbox service (``gclaw-sandbox``) accepts POST /execute with a
JSON body {code, runtime, timeout_seconds, memory_mb, network,
allowed_modules} and returns the standard result dict. This adapter
handles signed-JWT identity, request shaping, and structured error
surfacing — the sandbox itself is a separate Phase-6 follow-up
(infra/sandbox/).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 60.0


class RemoteRunner:
    def __init__(
        self,
        *,
        sandbox_url: str,
        identity_token_provider: Callable[[str], str | None],
        http_transport: Any | None = None,
    ) -> None:
        self._sandbox_url = sandbox_url.rstrip("/")
        self._token_provider = identity_token_provider
        self._transport = http_transport

    async def execute(self, *, code: str, config: Any) -> dict:
        start = time.perf_counter()
        try:
            token = self._token_provider(self._sandbox_url)
        except Exception as e:
            return _fail(
                error=f"identity token provider failed: {e}",
                duration_ms=int((time.perf_counter() - start) * 1000),
            )
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        body = {
            "code": code,
            "runtime": getattr(config, "runtime", "python3.12"),
            "timeout_seconds": getattr(config, "timeout_seconds", 30),
            "memory_mb": getattr(config, "memory_mb", 256),
            "network": getattr(config, "network", "none"),
            "allowed_modules": getattr(config, "allowed_modules", []) or [],
        }

        client_kwargs: dict[str, Any] = {"timeout": _DEFAULT_TIMEOUT_SECONDS}
        if self._transport is not None:
            client_kwargs["transport"] = self._transport

        try:
            async with httpx.AsyncClient(**client_kwargs) as client:
                resp = await client.post(
                    f"{self._sandbox_url}/execute",
                    json=body,
                    headers=headers,
                )
        except Exception as e:
            return _fail(
                error=f"HTTP call to sandbox failed: {e}",
                duration_ms=int((time.perf_counter() - start) * 1000),
            )

        if resp.status_code >= 400:
            return _fail(
                error=f"sandbox returned HTTP {resp.status_code}: {resp.text[:500]}",
                duration_ms=int((time.perf_counter() - start) * 1000),
            )
        try:
            data = resp.json()
        except Exception as e:
            return _fail(
                error=f"sandbox returned non-JSON body: {e}",
                duration_ms=int((time.perf_counter() - start) * 1000),
            )

        # Trust the sandbox's self-reported fields; fill in missing
        # keys with sane defaults rather than KeyErroring.
        return {
            "stdout": data.get("stdout", ""),
            "stderr": data.get("stderr", ""),
            "exit_code": int(data.get("exit_code", 0)),
            "duration_ms": int(data.get("duration_ms", 0)),
            "truncated": bool(data.get("truncated", False)),
        }


def _fail(*, error: str, duration_ms: int, exit_code: int = 1) -> dict:
    return {
        "stdout": "",
        "stderr": "",
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "truncated": False,
        "error": error,
    }
