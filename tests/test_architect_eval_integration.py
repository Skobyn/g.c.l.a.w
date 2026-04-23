"""Integration tests for the architect's eval feedback loop (ADR-0006).

Covers ``generate_starter_evalset`` + ``run_eval_against_draft`` and a
smoke pass of the full pipeline (clarify → draft → stage → eval →
approve → register) with everything mocked.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from gclaw.eval.evalset import EvalCaseResult, EvalRunResult, MetricScore
from gclaw.tools import agent_architect_tools as aat


# ── shared fixtures ───────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_module_globals():
    aat.set_agent_config_service(None)
    aat.set_agent_factory(None)
    aat.set_judge_ask_fn(None)
    aat.set_judge_model("gemini-2.5-flash")
    # Reset cached tool registry so each test starts fresh.
    aat._TOOL_REGISTRY = None
    yield
    aat.set_agent_config_service(None)
    aat.set_agent_factory(None)
    aat.set_judge_ask_fn(None)
    aat._TOOL_REGISTRY = None


@pytest.fixture
def evalsets_dir(tmp_path: Path, monkeypatch) -> Path:
    """Redirect starter evalsets to a tmp dir so tests don't pollute
    the repo's tests/eval/evalsets/."""
    out = tmp_path / "evalsets"
    out.mkdir()
    monkeypatch.setenv("GCLAW_EVALSETS_DIR", str(out))
    return out


def _stub_judge_with(json_payload: dict):
    """Inject a fake judge ask_fn that returns ``json_payload`` as a
    JSON-encoded string wrapped in a {score, rationale, ...} envelope.

    The starter-evalset parser extracts the ``cases`` list directly;
    we encode the whole payload (cases + a token score) so the
    JudgeClient's verdict parser is also satisfied.
    """
    payload = dict(json_payload)
    payload.setdefault("score", 1.0)
    payload.setdefault("rationale", "ok")

    async def _ask(_prompt: str) -> str:
        return json.dumps(payload)

    aat.set_judge_ask_fn(_ask)


# ── generate_starter_evalset ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_starter_evalset_writes_file(evalsets_dir):
    cases = [
        {
            "case_id": "balance-summary",
            "input": "Summarize my checking balance.",
            "agent_name": "finance-mgr",
            "expected_tool_uses": [
                {"name": "fetch_balance", "args_match": {"account_id": ".*"}}
            ],
            "expected_response": {
                "match_type": "rubric_based_final_response_quality_v1",
                "rubric": "Cites a dollar figure.",
            },
        }
    ]
    _stub_judge_with({"cases": cases})

    result = await aat.generate_starter_evalset(
        agent_name="finance-mgr",
        body="You summarize Plaid balances.",
        tools_declared=["fetch_balance"],
        case_count=1,
    )
    assert result.startswith("OK:")
    out_path = evalsets_dir / "finance-mgr.json"
    assert out_path.exists()

    with open(out_path) as f:
        evalset_doc = json.load(f)
    assert evalset_doc["name"] == "finance-mgr"
    assert evalset_doc["judge_model"] == "gemini-2.5-flash"
    assert len(evalset_doc["cases"]) == 1
    assert evalset_doc["cases"][0]["case_id"] == "balance-summary"


@pytest.mark.asyncio
async def test_generate_starter_evalset_respects_case_count(evalsets_dir):
    """Whatever the judge returns is the truth; the parser does not
    truncate. We assert the evalset passes the judge's ``cases`` list
    through verbatim so callers can verify the count."""
    cases = [
        {
            "case_id": f"case-{i}",
            "input": f"input {i}",
            "agent_name": "demo-mgr",
            "expected_tool_uses": [],
            "expected_response": {
                "match_type": "rubric_based_final_response_quality_v1",
                "rubric": "ok",
            },
        }
        for i in range(3)
    ]
    _stub_judge_with({"cases": cases})

    result = await aat.generate_starter_evalset(
        agent_name="demo-mgr",
        body="Demo body",
        tools_declared=[],
        case_count=3,
    )
    assert "(3 cases)" in result
    out_path = evalsets_dir / "demo-mgr.json"
    with open(out_path) as f:
        evalset_doc = json.load(f)
    assert len(evalset_doc["cases"]) == 3


@pytest.mark.asyncio
async def test_generate_starter_evalset_rejects_empty_body(evalsets_dir):
    out = await aat.generate_starter_evalset(
        agent_name="finance-mgr",
        body="",
        tools_declared=[],
    )
    assert out.startswith("ERROR")


@pytest.mark.asyncio
async def test_generate_starter_evalset_handles_unparseable_judge(
    evalsets_dir,
):
    async def _ask(_prompt: str) -> str:
        return "not valid json at all"

    aat.set_judge_ask_fn(_ask)
    out = await aat.generate_starter_evalset(
        agent_name="finance-mgr",
        body="body",
        tools_declared=[],
    )
    assert out.startswith("ERROR")


# ── run_eval_against_draft ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_eval_against_draft_uses_transient_factory(
    evalsets_dir, tmp_path
):
    """The eval path must build the ephemeral agent via
    ``factory.build_transient`` with the body + soul + resolved tools."""
    # Pre-seed an evalset on disk so we don't have to mock the loader.
    evalset_path = evalsets_dir / "demo-mgr.json"
    evalset_path.write_text(json.dumps({
        "name": "demo-mgr",
        "judge_model": "gemini-2.5-flash",
        "cases": [
            {
                "case_id": "demo-case",
                "input": "demo input",
                "agent_name": "demo-mgr",
                "expected_tool_uses": [],
                "expected_response": {
                    "match_type": "rubric_based_final_response_quality_v1",
                    "rubric": "ok",
                },
            }
        ],
    }))

    fake_factory = MagicMock()
    fake_factory.build_transient.return_value = MagicMock(
        name="transient_agent_mock"
    )
    aat.set_agent_factory(fake_factory)

    # Patch EvalRunner so we don't actually invoke ADK.
    fake_run = EvalRunResult(
        evalset_name="demo-mgr",
        started_at="2026-04-22T22:30:00+00:00",
        finished_at="2026-04-22T22:30:05+00:00",
        judge_model="gemini-2.5-flash",
        cases=[EvalCaseResult(
            case_id="demo-case", agent_name="demo-mgr", input="demo input",
            metrics=[MetricScore(
                metric="rubric_based_final_response_quality_v1", score=0.95
            )],
        )],
        metric_averages={"rubric_based_final_response_quality_v1": 0.95},
    )

    import gclaw.eval.evalset_runner as runner_mod

    fake_runner = MagicMock()
    fake_runner.run_evalset = AsyncMock(return_value=fake_run)
    monkey_factory = MagicMock(return_value=fake_runner)
    real_eval_runner = runner_mod.EvalRunner
    runner_mod.EvalRunner = monkey_factory
    try:
        out = await aat.run_eval_against_draft(
            agent_name="demo-mgr",
            body="You are demo.",
            soul_overlay="",
            tools_declared=[],
            evalset_path=str(evalset_path),
        )
    finally:
        runner_mod.EvalRunner = real_eval_runner

    # build_transient was called with the right shape.
    fake_factory.build_transient.assert_called_once()
    kwargs = fake_factory.build_transient.call_args.kwargs
    assert kwargs["agent_name"] == "demo-mgr"
    assert kwargs["body"] == "You are demo."
    # Empty overlay coerces to None so the loader skips the overlay
    # file lookup entirely.
    assert kwargs["soul_overlay"] is None
    assert kwargs["tools"] == []

    # The output is a formatted block, not an error.
    assert not out.startswith("ERROR")
    assert "DRAFT READY" in out


@pytest.mark.asyncio
async def test_run_eval_against_draft_returns_formatted_block(
    evalsets_dir, tmp_path
):
    """Score table format must match the ADR-0006 approval payload."""
    evalset_path = evalsets_dir / "demo-mgr.json"
    evalset_path.write_text(json.dumps({
        "name": "demo-mgr",
        "judge_model": "gemini-2.5-flash",
        "cases": [
            {
                "case_id": "c1",
                "input": "i",
                "agent_name": "demo-mgr",
                "expected_tool_uses": [],
                "expected_response": {
                    "match_type": "rubric_based_final_response_quality_v1",
                    "rubric": "ok",
                },
            }
        ],
    }))

    fake_factory = MagicMock()
    fake_factory.build_transient.return_value = MagicMock()
    aat.set_agent_factory(fake_factory)

    fake_run = EvalRunResult(
        evalset_name="demo-mgr",
        started_at="x",
        finished_at="y",
        judge_model="gemini-2.5-flash",
        cases=[],
        metric_averages={
            "tool_trajectory_avg_score": 0.92,
            "final_response_match_v2": 0.81,
            "hallucinations_v1": 1.0,
        },
    )
    import gclaw.eval.evalset_runner as runner_mod

    fake_runner = MagicMock()
    fake_runner.run_evalset = AsyncMock(return_value=fake_run)
    real_runner = runner_mod.EvalRunner
    runner_mod.EvalRunner = MagicMock(return_value=fake_runner)
    try:
        out = await aat.run_eval_against_draft(
            agent_name="demo-mgr",
            body="You are demo.",
            soul_overlay="",
            tools_declared=[],
            evalset_path=str(evalset_path),
        )
    finally:
        runner_mod.EvalRunner = real_runner

    # The block carries the ADR-0006-shaped header + each metric line
    # + the recommendation footer.
    assert "DRAFT READY: demo-mgr" in out
    assert "Eval (1 cases, judge=gemini-2.5-flash):" in out
    assert "tool_trajectory_avg_score" in out
    assert "0.92" in out
    assert "final_response_match_v2" in out
    assert "0.81" in out
    assert "hallucinations_v1" in out
    assert "1.00" in out
    assert "APPROVE" in out


@pytest.mark.asyncio
async def test_run_eval_against_draft_warns_on_low_score(
    evalsets_dir,
):
    """Scores below threshold should flip the recommendation to
    REVISE and emit a per-metric WARN line."""
    evalset_path = evalsets_dir / "demo-mgr.json"
    evalset_path.write_text(json.dumps({
        "name": "demo-mgr",
        "judge_model": "gemini-2.5-flash",
        "cases": [
            {"case_id": "c1", "input": "i", "agent_name": "demo-mgr",
             "expected_tool_uses": []}
        ],
    }))

    fake_factory = MagicMock()
    fake_factory.build_transient.return_value = MagicMock()
    aat.set_agent_factory(fake_factory)

    fake_run = EvalRunResult(
        evalset_name="demo-mgr", started_at="x", finished_at="y",
        judge_model="gemini-2.5-flash", cases=[],
        metric_averages={"tool_trajectory_avg_score": 0.42},
    )
    import gclaw.eval.evalset_runner as runner_mod
    fake_runner = MagicMock()
    fake_runner.run_evalset = AsyncMock(return_value=fake_run)
    real_runner = runner_mod.EvalRunner
    runner_mod.EvalRunner = MagicMock(return_value=fake_runner)
    try:
        out = await aat.run_eval_against_draft(
            agent_name="demo-mgr",
            body="You are demo.",
            soul_overlay="",
            tools_declared=[],
            evalset_path=str(evalset_path),
        )
    finally:
        runner_mod.EvalRunner = real_runner

    assert "WARN: tool_trajectory_avg_score" in out
    assert "REVISE" in out


@pytest.mark.asyncio
async def test_run_eval_against_draft_rejects_unknown_tool(
    evalsets_dir,
):
    """v1 only resolves tools already bound to a manager."""
    evalset_path = evalsets_dir / "demo-mgr.json"
    evalset_path.write_text(json.dumps({
        "name": "demo-mgr", "judge_model": "gemini-2.5-flash", "cases": [],
    }))
    aat.set_agent_factory(MagicMock())
    out = await aat.run_eval_against_draft(
        agent_name="demo-mgr",
        body="b",
        soul_overlay="",
        tools_declared=["this_tool_does_not_exist"],
        evalset_path=str(evalset_path),
    )
    assert out.startswith("ERROR")
    assert "this_tool_does_not_exist" in out


@pytest.mark.asyncio
async def test_run_eval_against_draft_resolves_known_tool(
    evalsets_dir, tmp_path
):
    """Known tool names from the manager modules resolve to callables
    and are passed into ``factory.build_transient`` as the tools list."""
    evalset_path = evalsets_dir / "demo-mgr.json"
    evalset_path.write_text(json.dumps({
        "name": "demo-mgr",
        "judge_model": "gemini-2.5-flash",
        "cases": [
            {"case_id": "c1", "input": "i", "agent_name": "demo-mgr",
             "expected_tool_uses": []}
        ],
    }))

    fake_factory = MagicMock()
    fake_factory.build_transient.return_value = MagicMock()
    aat.set_agent_factory(fake_factory)

    fake_run = EvalRunResult(
        evalset_name="demo-mgr", started_at="x", finished_at="y",
        judge_model="gemini-2.5-flash", cases=[], metric_averages={},
    )
    import gclaw.eval.evalset_runner as runner_mod
    fake_runner = MagicMock()
    fake_runner.run_evalset = AsyncMock(return_value=fake_run)
    real_runner = runner_mod.EvalRunner
    runner_mod.EvalRunner = MagicMock(return_value=fake_runner)
    try:
        out = await aat.run_eval_against_draft(
            agent_name="demo-mgr",
            body="b",
            soul_overlay="",
            # web_search is a real research_tools function; should resolve.
            tools_declared=["web_search"],
            evalset_path=str(evalset_path),
        )
    finally:
        runner_mod.EvalRunner = real_runner

    assert not out.startswith("ERROR")
    kwargs = fake_factory.build_transient.call_args.kwargs
    assert len(kwargs["tools"]) == 1
    # Resolved callable's name should match the declared name.
    assert getattr(kwargs["tools"][0], "__name__", "") == "web_search"


@pytest.mark.asyncio
async def test_run_eval_against_draft_missing_evalset(evalsets_dir):
    aat.set_agent_factory(MagicMock())
    out = await aat.run_eval_against_draft(
        agent_name="demo-mgr",
        body="b",
        soul_overlay="",
        tools_declared=[],
        evalset_path=str(evalsets_dir / "nope.json"),
    )
    assert out.startswith("ERROR")
    assert "not found" in out


@pytest.mark.asyncio
async def test_run_eval_against_draft_requires_factory():
    """Without a wired AgentFactory, the tool refuses to run."""
    aat.set_agent_factory(None)
    with pytest.raises(RuntimeError, match="agent_factory not configured"):
        await aat.run_eval_against_draft(
            agent_name="demo-mgr",
            body="b",
            soul_overlay="",
            tools_declared=[],
            evalset_path="/tmp/nonexistent.json",
        )


# ── full pipeline smoke ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_full_architect_loop_smoke(
    evalsets_dir, tmp_path, monkeypatch
):
    """Smoke-test the architect's pipeline end-to-end with all I/O
    mocked: clarify (skipped) → draft → stage → eval → approve →
    register. Exercises the new tools alongside the existing ones to
    confirm they compose."""
    # Stand up a fake config dir so write_agent_file / write_soul_file
    # have somewhere to land.
    config_dir = tmp_path / "config"
    (config_dir / "agents").mkdir(parents=True)
    (config_dir / "soul").mkdir()
    monkeypatch.setenv("GCLAW_CONFIG_DIR", str(config_dir))

    # 1. Existing-agents check (collision detection).
    fake_svc = MagicMock()
    fake_svc.list_agents.return_value = [
        {"name": "workspace-mgr", "is_standalone": False,
         "has_override": False, "model_ref": None},
    ]
    aat.set_agent_config_service(fake_svc)

    listing = aat.list_registered_agents()
    assert "workspace-mgr" in listing
    assert "finance-mgr" not in listing  # name is free

    # 2. Generate starter evalset (judge stubbed).
    cases = [
        {
            "case_id": "balance-summary",
            "input": "What's my balance?",
            "agent_name": "finance-mgr",
            "expected_tool_uses": [
                {"name": "web_search", "args_match": {"query": ".*"}}
            ],
            "expected_response": {
                "match_type": "rubric_based_final_response_quality_v1",
                "rubric": "Mentions a dollar amount.",
            },
        }
    ]
    _stub_judge_with({"cases": cases})

    body = "You summarize Plaid balances using research tools."
    gen_out = await aat.generate_starter_evalset(
        agent_name="finance-mgr",
        body=body,
        tools_declared=["web_search"],
        case_count=1,
    )
    assert gen_out.startswith("OK:")
    evalset_path = evalsets_dir / "finance-mgr.json"
    assert evalset_path.exists()

    # 3. Run eval against the draft (factory + EvalRunner mocked).
    fake_factory = MagicMock()
    fake_factory.build_transient.return_value = MagicMock()
    aat.set_agent_factory(fake_factory)

    fake_run = EvalRunResult(
        evalset_name="finance-mgr", started_at="x", finished_at="y",
        judge_model="gemini-2.5-flash", cases=[],
        metric_averages={
            "tool_trajectory_avg_score": 0.95,
            "rubric_based_final_response_quality_v1": 0.88,
        },
    )
    import gclaw.eval.evalset_runner as runner_mod
    fake_runner = MagicMock()
    fake_runner.run_evalset = AsyncMock(return_value=fake_run)
    real_runner = runner_mod.EvalRunner
    runner_mod.EvalRunner = MagicMock(return_value=fake_runner)
    try:
        eval_out = await aat.run_eval_against_draft(
            agent_name="finance-mgr",
            body=body,
            soul_overlay="",
            tools_declared=["web_search"],
            evalset_path=str(evalset_path),
        )
    finally:
        runner_mod.EvalRunner = real_runner

    assert "DRAFT READY: finance-mgr" in eval_out
    assert "0.95" in eval_out
    assert "0.88" in eval_out
    assert "APPROVE" in eval_out
    fake_factory.build_transient.assert_called_once()

    # 4. Approve → register the standalone agent.
    fake_override = MagicMock()
    fake_override.agent_name = "finance-mgr"
    fake_override.model.primary = "gemini-2.5-flash"
    fake_svc.create_standalone.return_value = fake_override

    register_out = aat.register_standalone_agent(
        agent_name="finance-mgr",
        body=body,
        description="Plaid balance summarizer",
        model_primary="gemini-2.5-flash",
    )
    assert register_out.startswith("OK")
    fake_svc.create_standalone.assert_called_once()
    register_kwargs = fake_svc.create_standalone.call_args.kwargs
    assert register_kwargs["agent_name"] == "finance-mgr"
    assert register_kwargs["body"] == body


# ── helpers ───────────────────────────────────────────────────────────────


def test_resolve_tool_known_returns_callable():
    """The v1 registry indexes by ``__name__`` and resolves manager
    tools."""
    fn = aat._resolve_tool("web_search")
    assert callable(fn)
    assert getattr(fn, "__name__", "") == "web_search"


def test_resolve_tool_unknown_raises():
    with pytest.raises(ValueError, match="unknown tool name"):
        aat._resolve_tool("definitely_not_a_real_tool")


def test_resolve_tool_indexes_architect_own_tools():
    """The registry exposes the architect's own tools too — useful for
    drafts that want to inspect/list other agents."""
    fn = aat._resolve_tool("list_registered_agents")
    assert fn is aat.list_registered_agents


def test_format_eval_block_omits_score_warning_when_clean():
    fake_run = EvalRunResult(
        evalset_name="x", started_at="x", finished_at="y",
        judge_model="gemini-2.5-flash", cases=[],
        metric_averages={"tool_trajectory_avg_score": 0.9},
    )
    fake_evalset = MagicMock(cases=[MagicMock(), MagicMock()])
    out = aat._format_eval_block(
        agent_name="demo-mgr",
        evalset=fake_evalset,
        result=fake_run,
        judge_model="gemini-2.5-flash",
        tools_declared=["a", "b"],
    )
    assert "WARN" not in out
    assert "APPROVE" in out


def test_format_eval_block_handles_no_metrics():
    fake_run = EvalRunResult(
        evalset_name="x", started_at="x", finished_at="y",
        judge_model="gemini-2.5-flash", cases=[], metric_averages={},
    )
    fake_evalset = MagicMock(cases=[])
    out = aat._format_eval_block(
        agent_name="demo-mgr",
        evalset=fake_evalset,
        result=fake_run,
        judge_model="gemini-2.5-flash",
        tools_declared=[],
    )
    # Empty averages → "no metrics applied" hint, recommendation still
    # defaults to APPROVE since there are no failing scores.
    assert "no metrics applied" in out
