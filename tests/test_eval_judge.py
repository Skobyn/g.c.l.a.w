"""Tests for the JudgeClient — verdict parsing + per-run cache."""

from __future__ import annotations

import pytest

from gclaw.eval.judge import JudgeClient, _parse_verdict


def test_parse_verdict_plain_json():
    v = _parse_verdict('{"score": 0.7, "rationale": "ok"}')
    assert v.score == 0.7
    assert v.rationale == "ok"


def test_parse_verdict_json_in_markdown_fence():
    raw = '```json\n{"score": 0.4, "rationale": "meh"}\n```'
    v = _parse_verdict(raw)
    assert v.score == 0.4
    assert v.rationale == "meh"


def test_parse_verdict_extracts_first_object_from_prose():
    raw = (
        "Sure thing — here is my judgement:\n"
        '{"score": 1.0, "rationale": "perfect"}\n'
        "Let me know if you need anything else."
    )
    v = _parse_verdict(raw)
    assert v.score == 1.0
    assert v.rationale == "perfect"


def test_parse_verdict_clamps_out_of_range_scores():
    v = _parse_verdict('{"score": 1.7, "rationale": "too hot"}')
    assert v.score == 1.0
    v_neg = _parse_verdict('{"score": -0.3, "rationale": "too cold"}')
    assert v_neg.score == 0.0


def test_parse_verdict_falls_back_to_zero_when_unparsable():
    v = _parse_verdict("definitely not JSON")
    assert v.score == 0.0
    assert "definitely" in v.rationale


@pytest.mark.asyncio
async def test_judge_client_caches_verdicts():
    """Same (input, response, rubric) tuple → judge called once."""
    calls = {"n": 0}

    async def fake_ask(prompt: str) -> str:
        calls["n"] += 1
        return '{"score": 0.5, "rationale": "stub"}'

    judge = JudgeClient(ask_fn=fake_ask)
    a = await judge.ask(
        input_="ping", response="pong", rubric="r1", prompt="prompt-1"
    )
    b = await judge.ask(
        input_="ping", response="pong", rubric="r1", prompt="prompt-1"
    )
    assert a == b
    assert calls["n"] == 1
    assert judge.call_count == 1
    assert judge.cache_size == 1


@pytest.mark.asyncio
async def test_judge_client_keys_on_input_response_rubric_only():
    """Cache key ignores prompt — same trio with a different prompt is a hit."""
    calls = {"n": 0}

    async def fake_ask(prompt: str) -> str:
        calls["n"] += 1
        return '{"score": 0.42}'

    judge = JudgeClient(ask_fn=fake_ask)
    await judge.ask(
        input_="i", response="r", rubric="rubric", prompt="P1"
    )
    await judge.ask(
        input_="i", response="r", rubric="rubric", prompt="P2-different"
    )
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_judge_client_distinct_keys_distinct_calls():
    """Different rubrics over the same response → two distinct calls."""
    calls = {"n": 0}

    async def fake_ask(prompt: str) -> str:
        calls["n"] += 1
        return '{"score": 0.5}'

    judge = JudgeClient(ask_fn=fake_ask)
    await judge.ask(input_="i", response="r", rubric="A", prompt="p")
    await judge.ask(input_="i", response="r", rubric="B", prompt="p")
    assert calls["n"] == 2
    assert judge.cache_size == 2
