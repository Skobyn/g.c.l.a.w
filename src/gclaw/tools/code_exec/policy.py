"""AST-based pre-flight policy check for Python code snippets.

Lightweight — scans top-level imports only. Catches the obvious
``import socket`` / ``from requests import get`` attempts; does NOT
attempt to catch dynamic ``importlib`` routes or ``__import__``
tricks. A true sandbox (Phase 6 remote runner via Cloud Run) is the
real enforcement boundary; this is a speed bump for local dev.
"""

from __future__ import annotations

import ast

_DEFAULT_NETWORK_BLOCKLIST = frozenset(
    {
        "socket",
        "ssl",
        "urllib",
        "urllib3",
        "http",
        "httpx",
        "requests",
        "aiohttp",
        "websocket",
        "websockets",
        "ftplib",
        "smtplib",
        "telnetlib",
    }
)


class NetworkPolicyViolation(RuntimeError):
    """Raised when Python source imports a network module under
    ``network='none'`` and the module isn't in ``allowed_modules``."""


def check_python_source(
    source: str,
    *,
    network: str = "none",
    allowed_modules: list[str] | None = None,
) -> None:
    """Raise ``NetworkPolicyViolation`` when the source violates policy.

    Silent on success. ``network='egress-only'`` bypasses the scan.
    ``allowed_modules`` is an explicit whitelist that wins over the
    blocklist — the escape hatch for network-enabled sandboxes that
    still want surface-level verification of user input.
    """
    if network != "none":
        return
    allowed = set(allowed_modules or [])
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Let the runner surface syntax errors — policy is orthogonal.
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in _DEFAULT_NETWORK_BLOCKLIST and root not in allowed:
                    raise NetworkPolicyViolation(
                        f"network module {root!r} is blocked under network='none'"
                    )
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in _DEFAULT_NETWORK_BLOCKLIST and root not in allowed:
                raise NetworkPolicyViolation(
                    f"network module {root!r} is blocked under network='none'"
                )
