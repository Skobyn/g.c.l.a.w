"""Tests for three-tier context compaction."""

import pytest
from gclaw.session.compaction import CompactionStrategy, CompactionResult, ContextCompactor


def test_compaction_strategy_values():
    assert CompactionStrategy.MICRO == "micro"
    assert CompactionStrategy.AUTO == "auto"
    assert CompactionStrategy.FULL == "full"


def test_compaction_result():
    result = CompactionResult(
        strategy=CompactionStrategy.MICRO,
        messages_before=50,
        messages_after=20,
        summary=None,
    )
    assert result.tokens_saved == 0


def test_context_compactor_select_micro():
    compactor = ContextCompactor(
        micro_threshold=30,
        auto_threshold=50,
        full_threshold=80,
    )
    strategy = compactor.select_strategy(message_count=35)
    assert strategy == CompactionStrategy.MICRO


def test_context_compactor_select_auto():
    compactor = ContextCompactor(
        micro_threshold=30,
        auto_threshold=50,
        full_threshold=80,
    )
    strategy = compactor.select_strategy(message_count=55)
    assert strategy == CompactionStrategy.AUTO


def test_context_compactor_select_full():
    compactor = ContextCompactor(
        micro_threshold=30,
        auto_threshold=50,
        full_threshold=80,
    )
    strategy = compactor.select_strategy(message_count=85)
    assert strategy == CompactionStrategy.FULL


def test_context_compactor_below_threshold():
    compactor = ContextCompactor(
        micro_threshold=30,
        auto_threshold=50,
        full_threshold=80,
    )
    strategy = compactor.select_strategy(message_count=10)
    assert strategy is None


def test_micro_compact():
    compactor = ContextCompactor(
        micro_threshold=30,
        auto_threshold=50,
        full_threshold=80,
    )
    messages = [f"msg-{i}" for i in range(40)]
    result = compactor.micro_compact(messages, keep_recent=20)
    assert result.strategy == CompactionStrategy.MICRO
    assert result.messages_after == 20
    assert result.kept_messages == messages[-20:]


def test_micro_compact_preserves_system():
    compactor = ContextCompactor(
        micro_threshold=30,
        auto_threshold=50,
        full_threshold=80,
    )
    messages = ["[system] init"] + [f"msg-{i}" for i in range(40)]
    result = compactor.micro_compact(messages, keep_recent=10, preserve_system=True)
    assert result.kept_messages[0] == "[system] init"
    assert len(result.kept_messages) == 11


def test_circuit_breaker_trips():
    compactor = ContextCompactor(
        micro_threshold=30,
        auto_threshold=50,
        full_threshold=80,
        max_consecutive_failures=3,
    )
    compactor.record_failure()
    compactor.record_failure()
    compactor.record_failure()
    assert compactor.circuit_open is True


def test_circuit_breaker_resets_on_success():
    compactor = ContextCompactor(
        micro_threshold=30,
        auto_threshold=50,
        full_threshold=80,
        max_consecutive_failures=3,
    )
    compactor.record_failure()
    compactor.record_failure()
    compactor.record_success()
    assert compactor.circuit_open is False
    assert compactor._consecutive_failures == 0
