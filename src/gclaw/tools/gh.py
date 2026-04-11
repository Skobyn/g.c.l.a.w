"""Async subprocess helper for the GitHub CLI (`gh`).

`gh` supports both JSON output (via --json flags) and raw text output
(e.g. `gh pr diff`), so this helper supports both modes via `parse_json`.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class GhError(RuntimeError):
    """Raised when a gh invocation fails, times out, or returns invalid JSON."""


async def run_gh(
    *args: str,
    timeout: float = 30.0,
    parse_json: bool = True,
) -> Any:
    """Run the gh CLI and return parsed output.

    Args:
        *args: positional arguments passed verbatim to the gh binary.
        timeout: seconds to wait before killing the process.
        parse_json: if True (default), parse stdout as JSON.
                    if False, return stdout as a stripped string.

    Returns:
        Parsed JSON (list/dict) if parse_json=True, else a string.

    Raises:
        GhError: on non-zero exit code, invalid JSON, or timeout.
    """
    logger.debug("Running: gh %s", " ".join(args))
    proc = await asyncio.create_subprocess_exec(
        "gh", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError as e:
        proc.kill()
        raise GhError(
            f"gh {' '.join(args)} timed out after {timeout}s"
        ) from e

    if proc.returncode != 0:
        err = stderr.decode(errors="replace").strip()
        raise GhError(
            f"gh {' '.join(args)} exited {proc.returncode}: {err}"
        )

    text = stdout.decode(errors="replace").strip()

    if not parse_json:
        return text

    if not text:
        return {}

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise GhError(
            f"gh {' '.join(args)} returned non-JSON output: {e}"
        ) from e
