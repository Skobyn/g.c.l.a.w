"""Tests for the code-exec AST-scan policy check."""

from __future__ import annotations

import pytest

from gclaw.tools.code_exec.policy import (
    NetworkPolicyViolation,
    check_python_source,
)


def test_allows_math_and_json():
    # Non-network imports pass.
    check_python_source("import json\nimport math\nprint(math.sqrt(4))")


def test_blocks_socket_when_network_none():
    with pytest.raises(NetworkPolicyViolation) as exc:
        check_python_source("import socket\ns = socket.socket()")
    assert "socket" in str(exc.value)


def test_blocks_urllib_when_network_none():
    with pytest.raises(NetworkPolicyViolation):
        check_python_source("import urllib.request\nurllib.request.urlopen('x')")


def test_blocks_from_requests_when_network_none():
    with pytest.raises(NetworkPolicyViolation):
        check_python_source("from requests import get")


def test_allows_all_when_network_egress_only():
    check_python_source(
        "import socket\ns = socket.socket()", network="egress-only"
    )


def test_allowed_modules_whitelist_permits_extra():
    # Network-forbidden import still passes when user explicitly
    # allowed it via allowed_modules (escape hatch for constrained
    # network-enabled sandboxes).
    check_python_source(
        "import socket",
        network="none",
        allowed_modules=["socket"],
    )


def test_ignores_strings_that_look_like_imports():
    # False-positive guard: the AST-level check only flags actual
    # import statements, not mentions in strings or docstrings.
    src = '''"""This talks about `import socket` in the docstring."""\nx = 1\n'''
    check_python_source(src)  # should not raise
