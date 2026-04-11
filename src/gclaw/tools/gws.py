"""Async subprocess helper for the Google Workspace CLI (`gws`).

Wraps `gws` invocations, parses structured JSON output, and raises
`GwsError` on non-zero exit, invalid JSON, or timeout.
"""

from __future__ import annotations

import asyncio
import json
import logging

logger = logging.getLogger(__name__)


class GwsError(RuntimeError):
    """Raised when a gws invocation fails, times out, or returns invalid JSON."""


async def run_gws(*args: str, timeout: float = 30.0) -> dict:
    """Run the gws CLI and return parsed JSON stdout.

    Args:
        *args: positional arguments passed verbatim to the gws binary.
        timeout: seconds to wait before killing the process.

    Returns:
        Parsed JSON object from stdout, or {} if stdout is empty.

    Raises:
        GwsError: on non-zero exit code, invalid JSON, or timeout.
    """
    logger.debug("Running: gws %s", " ".join(args))
    proc = await asyncio.create_subprocess_exec(
        "gws", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError as e:
        proc.kill()
        raise GwsError(
            f"gws {' '.join(args)} timed out after {timeout}s"
        ) from e

    if proc.returncode != 0:
        err = stderr.decode(errors="replace").strip()
        raise GwsError(
            f"gws {' '.join(args)} exited {proc.returncode}: {err}"
        )

    if not stdout:
        return {}

    try:
        return json.loads(stdout)
    except json.JSONDecodeError as e:
        raise GwsError(
            f"gws {' '.join(args)} returned non-JSON output: {e}"
        ) from e
