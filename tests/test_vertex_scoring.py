"""Unit tests for the Vertex Gen AI scoring service.

The SDK import is stubbed — tests prove the wrapper's fail-soft
behaviour and injected-client path without requiring live Vertex.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from gclaw.eval.vertex_scoring_service import (
    ScoringResult,
    ScoringSample,
    VertexScoringService,
)


def test_disabled_returns_unavailable_without_trying_to_import():
    svc = VertexScoringService(enabled=False)
    assert svc.enabled is False
    assert svc.is_available() is False


def test_enabled_without_project_id_still_disabled():
    svc = VertexScoringService(enabled=True, project=None)
    assert svc.enabled is False


@pytest.mark.asyncio
async def test_score_batch_empty_returns_empty_list():
    svc = VertexScoringService(
        enabled=True, project="p", client=MagicMock()
    )
    assert await svc.score_batch([]) == []


@pytest.mark.asyncio
async def test_score_batch_when_unavailable_returns_error_per_sample():
    svc = VertexScoringService(enabled=False)
    samples = [
        ScoringSample(span_id="s1", response="answer"),
        ScoringSample(span_id="s2", response="other"),
    ]
    results = await svc.score_batch(samples)
    assert len(results) == 2
    assert all(r.error == "vertex scoring unavailable" for r in results)
    assert [r.span_id for r in results] == ["s1", "s2"]


@pytest.mark.asyncio
async def test_score_batch_uses_injected_client_scores():
    client = MagicMock()
    client.score.side_effect = [
        {"groundedness": 0.9, "coherence": 0.8, "tool_use_quality": 0.7},
        {"groundedness": 0.1, "coherence": 0.2, "tool_use_quality": 0.3},
    ]
    svc = VertexScoringService(
        enabled=True, project="p", client=client
    )
    results = await svc.score_batch(
        [
            ScoringSample(span_id="s1", response="a", context="ctx-a"),
            ScoringSample(span_id="s2", response="b"),
        ]
    )
    assert len(results) == 2
    assert results[0].scores["groundedness"] == 0.9
    assert results[1].scores["coherence"] == 0.2
    assert client.score.call_count == 2


@pytest.mark.asyncio
async def test_score_batch_fails_soft_on_client_exception():
    client = MagicMock()
    client.score.side_effect = RuntimeError("vertex down")
    svc = VertexScoringService(
        enabled=True, project="p", client=client
    )
    results = await svc.score_batch(
        [ScoringSample(span_id="s1", response="a")]
    )
    assert len(results) == 1
    assert results[0].error == "vertex down"
    assert results[0].scores == {}


def test_scoring_result_serializes_to_firestore_dict():
    r = ScoringResult(
        span_id="abc",
        scores={"groundedness": 0.8},
        error=None,
    )
    d = r.to_firestore_dict()
    assert d == {"span_id": "abc", "scores": {"groundedness": 0.8}, "error": None}
