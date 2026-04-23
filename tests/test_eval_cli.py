"""Tests for the ``gclaw-eval`` CLI."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from gclaw.cli import eval as eval_cli
from gclaw.dispatch.runner import AgentResponse
from gclaw.eval.evalset import (
    EvalCase,
    EvalCaseResult,
    EvalRunResult,
    Evalset,
    MetricScore,
    ResponseMatch,
    ToolUseExpectation,
)


def _stub_runner(tool_calls=(), text="canned"):
    runner = MagicMock()

    async def _run_trace(*, user_id, session_id, message):
        return (
            AgentResponse(
                text=text,
                tool_calls=list(tool_calls),
                is_final=True,
            ),
            None,
        )

    runner.run_trace = AsyncMock(side_effect=_run_trace)
    return runner


def _write_evalset(path: Path) -> None:
    es = Evalset(
        name="cli-demo",
        cases=[
            EvalCase(
                case_id="c1",
                input="hi",
                agent_name="research-mgr",
                expected_tool_uses=[ToolUseExpectation(name="t")],
                expected_response=ResponseMatch(
                    expected="hi", mode="substring"
                ),
            )
        ],
    )
    es.to_json(path)


def test_cli_run_single_evalset(tmp_path, monkeypatch, capsys):
    """`gclaw-eval run --evalset PATH` exits 0 and writes a result file."""
    evalset_path = tmp_path / "ev.json"
    _write_evalset(evalset_path)
    results_dir = tmp_path / "results"

    # Patch the factory so the CLI doesn't need a real config dir.
    monkeypatch.setattr(
        eval_cli, "_build_minimal_factory", lambda config_dir: MagicMock()
    )
    # Patch the runner-builder hook so the EvalRunner uses our stub.
    from gclaw.eval import evalset_runner as runner_mod

    original_init = runner_mod.EvalRunner.__init__

    def patched_init(self, factory=None, **kwargs):
        kwargs.setdefault(
            "runner_builder",
            lambda case: _stub_runner(
                tool_calls=[{"name": "t", "args": {}}],
                text="hi there",
            ),
        )
        original_init(self, factory=factory, **kwargs)

    monkeypatch.setattr(runner_mod.EvalRunner, "__init__", patched_init)

    rc = eval_cli.main(
        [
            "run",
            "--evalset",
            str(evalset_path),
            "--results-dir",
            str(results_dir),
            "--config",
            str(tmp_path),
        ]
    )
    assert rc == 0

    files = list(results_dir.glob("cli-demo-*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text())
    assert payload["evalset_name"] == "cli-demo"
    out = capsys.readouterr().out
    assert "Evalset: cli-demo" in out


def test_cli_run_all_glob(tmp_path, monkeypatch):
    evalsets_dir = tmp_path / "evalsets"
    evalsets_dir.mkdir()
    _write_evalset(evalsets_dir / "one.json")
    _write_evalset(evalsets_dir / "two.json")
    results_dir = tmp_path / "results"

    monkeypatch.setattr(
        eval_cli, "_build_minimal_factory", lambda config_dir: MagicMock()
    )
    from gclaw.eval import evalset_runner as runner_mod
    original_init = runner_mod.EvalRunner.__init__

    def patched_init(self, factory=None, **kwargs):
        kwargs.setdefault(
            "runner_builder",
            lambda case: _stub_runner(
                tool_calls=[{"name": "t", "args": {}}], text="hi"
            ),
        )
        original_init(self, factory=factory, **kwargs)

    monkeypatch.setattr(runner_mod.EvalRunner, "__init__", patched_init)

    rc = eval_cli.main(
        [
            "run",
            "--all",
            "--evalsets-dir",
            str(evalsets_dir),
            "--results-dir",
            str(results_dir),
            "--config",
            str(tmp_path),
        ]
    )
    assert rc == 0
    assert len(list(results_dir.glob("cli-demo-*.json"))) == 2


def test_cli_compare_detects_regression(tmp_path):
    """A worse candidate must yield a non-zero exit."""
    baseline = EvalRunResult(
        evalset_name="x",
        started_at="2026-04-22T22:00:00+00:00",
        finished_at="2026-04-22T22:01:00+00:00",
        judge_model="gemini-2.5-flash",
        cases=[
            EvalCaseResult(
                case_id="c1",
                agent_name="a",
                input="i",
                metrics=[
                    MetricScore(metric="tool_trajectory_avg_score", score=1.0)
                ],
            )
        ],
        metric_averages={"tool_trajectory_avg_score": 1.0},
    )
    candidate = EvalRunResult(
        evalset_name="x",
        started_at="2026-04-22T22:10:00+00:00",
        finished_at="2026-04-22T22:11:00+00:00",
        judge_model="gemini-2.5-flash",
        cases=[
            EvalCaseResult(
                case_id="c1",
                agent_name="a",
                input="i",
                metrics=[
                    MetricScore(metric="tool_trajectory_avg_score", score=0.5)
                ],
            )
        ],
        metric_averages={"tool_trajectory_avg_score": 0.5},
    )
    base_path = tmp_path / "baseline.json"
    cand_path = tmp_path / "candidate.json"
    baseline.to_json(base_path)
    candidate.to_json(cand_path)

    rc = eval_cli.main(["compare", str(base_path), str(cand_path)])
    assert rc == 2  # regression > default threshold of 0.05


def test_cli_compare_passes_when_within_threshold(tmp_path):
    base = EvalRunResult(
        evalset_name="x",
        started_at="t1",
        finished_at="t2",
        judge_model="m",
        cases=[
            EvalCaseResult(
                case_id="c1",
                agent_name="a",
                input="i",
                metrics=[MetricScore(metric="x", score=0.9)],
            )
        ],
        metric_averages={"x": 0.9},
    )
    cand = EvalRunResult(
        evalset_name="x",
        started_at="t3",
        finished_at="t4",
        judge_model="m",
        cases=[
            EvalCaseResult(
                case_id="c1",
                agent_name="a",
                input="i",
                metrics=[MetricScore(metric="x", score=0.88)],
            )
        ],
        metric_averages={"x": 0.88},
    )
    bp = tmp_path / "b.json"
    cp = tmp_path / "c.json"
    base.to_json(bp)
    cand.to_json(cp)
    rc = eval_cli.main(
        ["compare", str(bp), str(cp), "--threshold", "0.05"]
    )
    assert rc == 0


def test_cli_help_runs(capsys):
    """`gclaw-eval --help` must work even without GCP credentials."""
    with pytest.raises(SystemExit) as exc:
        eval_cli.main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "gclaw-eval" in out
    assert "run" in out
    assert "compare" in out


def test_cli_run_missing_evalsets_dir(tmp_path, monkeypatch):
    """``--all`` against an empty directory must fail loudly."""
    monkeypatch.setattr(
        eval_cli, "_build_minimal_factory", lambda config_dir: MagicMock()
    )
    rc = eval_cli.main(
        [
            "run",
            "--all",
            "--evalsets-dir",
            str(tmp_path / "does-not-exist"),
            "--results-dir",
            str(tmp_path / "out"),
            "--config",
            str(tmp_path),
        ]
    )
    assert rc == 1
