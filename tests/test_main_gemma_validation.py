"""Tests for the Gemma endpoint_id validation helper in main.py.

Background: the first live run of the eval harness surfaced that
a common .env misconfiguration — `GEMMA_ENDPOINT_ID=gemma-4-26b-it`
(a Vertex AI Model Garden name, not a Gemini API model name) —
causes every workspace/home/research manager LLM call to fail with
"Model gemma-4-26b-it not found". The router now detects this and
skips registration with a loud warning instead of silently wiring
a broken endpoint.
"""

from __future__ import annotations

import pytest

from gclaw.main import _looks_like_gemini_api_gemma


@pytest.mark.parametrize(
    "value",
    [
        "gemma-3-27b-it",
        "gemma-3-12b-it",
        "gemma-3-4b-it",
        "gemma-3-1b-it",
        "gemma-2-27b-it",
        "gemma-2-9b-it",
        "gemma-2-2b-it",
        "models/gemma-3-27b-it",  # with "models/" prefix is also accepted
    ],
)
def test_known_valid_gemini_api_gemma_names(value):
    assert _looks_like_gemini_api_gemma(value) is True


@pytest.mark.parametrize(
    "value",
    [
        "",  # empty → skip
        None,  # pydantic settings should never produce this but be defensive
        "gemma-4-26b-it",  # Model Garden name — what shipped in .env.example
        "gemini-2.5-flash",  # wrong model family
        "gpt-4",  # wrong provider entirely
        "publishers/google/models/gemma-3-27b",  # Vertex AI Model Garden path
        "projects/foo/locations/us-central1/endpoints/123",  # Vertex endpoint ARN
        "anthropic/claude-3-sonnet",  # slash in id
    ],
)
def test_rejects_invalid_gemma_names(value):
    assert _looks_like_gemini_api_gemma(value) is False


def test_handles_none_defensively():
    """The helper should not raise on None even though the caller
    filters with `if settings.gemma_endpoint_id:` upstream."""
    assert _looks_like_gemini_api_gemma("") is False
