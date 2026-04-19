"""Sandboxed code execution for CODE_EXEC-kind tools.

Two runners share the same ``.execute(code, config) → result`` async
surface:
    - local_runner.LocalRunner   (subprocess + resource limits; dev)
    - remote_runner.RemoteRunner (signed-JWT HTTP to Cloud Run
      sibling ``gclaw-sandbox``)

main.py picks one based on settings.tool_code_exec_remote_url. Result
shape is uniform: {stdout, stderr, exit_code, duration_ms, truncated, error?}.
"""

from __future__ import annotations

from gclaw.tools.code_exec.local_runner import LocalRunner  # noqa: F401
from gclaw.tools.code_exec.policy import (  # noqa: F401
    NetworkPolicyViolation,
    check_python_source,
)
from gclaw.tools.code_exec.remote_runner import RemoteRunner  # noqa: F401
