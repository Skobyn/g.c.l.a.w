"""Tests for the builtin tool registry — @tool_export discovery + lookup."""

from __future__ import annotations

import pytest

from gclaw.tools.catalog.builtin_registry import (
    clear_registry_for_tests,
    get_registered,
    tool_export,
)


@pytest.fixture(autouse=True)
def _reset():
    clear_registry_for_tests()
    yield
    clear_registry_for_tests()


def test_decorator_records_function():
    @tool_export(description="A friendly greeter")
    def hello(name: str) -> str:
        """Say hello to someone."""
        return f"hi {name}"

    registry = get_registered()
    assert "hello" in registry
    entry = registry["hello"]
    assert entry.name == "hello"
    assert entry.description == "A friendly greeter"
    assert entry.function is hello
    # function_path is module:qualname-style.
    assert entry.function_path.endswith(".hello")


def test_decorator_preserves_callable_behavior():
    @tool_export()
    def echo(x: str) -> str:
        return x

    assert echo("abc") == "abc"


def test_decorator_custom_name():
    @tool_export(name="custom_id", description="…")
    def _internal(x: int) -> int:
        return x + 1

    registry = get_registered()
    assert "custom_id" in registry
    assert registry["custom_id"].function is _internal


def test_decorator_defaults_description_from_docstring():
    @tool_export()
    def documented(x: int) -> int:
        """Summarized first line.

        Longer body ignored.
        """
        return x

    registry = get_registered()
    entry = registry["documented"]
    assert entry.description == "Summarized first line."


def test_duplicate_name_raises():
    @tool_export()
    def duplicate_one():
        pass

    with pytest.raises(ValueError):
        @tool_export(name="duplicate_one")
        def duplicate_two():
            pass
