"""``gclaw-eval`` — argparse CLI driving the ADR-0005 evalset framework.

Three subcommands::

    gclaw-eval run --evalset PATH [--config PATH] [--results-dir PATH]
    gclaw-eval run --all                          # every tests/eval/evalsets/*.json
    gclaw-eval compare BASELINE CANDIDATE [--threshold 0.05]

The CLI deliberately bootstraps a *minimal* AgentFactory: it only needs
``ConfigLoader`` (and a ``--config`` directory pointing at ``agents/``
+ ``soul/``). Memory, board, catalog, and skill registry are all left
unset so eval can run in CI containers without Firestore credentials.
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from gclaw.eval.evalset import EvalRunResult, Evalset
from gclaw.eval.evalset_runner import EvalRunner

logger = logging.getLogger("gclaw-eval")


DEFAULT_EVALSETS_DIR = "tests/eval/evalsets"
DEFAULT_RESULTS_DIR = "tests/eval/results"
DEFAULT_REGRESSION_THRESHOLD = 0.05


# ── factory bootstrap ─────────────────────────────────────────────────────


def _build_minimal_factory(config_dir: str) -> Any:
    """Construct an ``AgentFactory`` with no Firestore dependencies.

    The factory needs a ``ConfigLoader`` rooted at ``config_dir`` (which
    must contain ``agents/`` and ``soul/`` subdirs as in production).
    Skills/catalog/memory are deliberately omitted — eval doesn't need
    them and they'd drag in GCP creds.
    """
    from gclaw.agents.factory import AgentFactory
    from gclaw.config.loader import ConfigLoader

    loader = ConfigLoader(config_dir=config_dir)
    return AgentFactory(loader=loader)


# ── `run` subcommand ──────────────────────────────────────────────────────


async def _run_evalset_path(
    path: str, factory: Any, results_dir: str
) -> tuple[EvalRunResult, Path]:
    evalset = Evalset.from_json(path)
    logger.info(
        "running evalset %s (%d cases) judge=%s",
        evalset.name,
        len(evalset.cases),
        evalset.judge_model,
    )
    runner = EvalRunner(factory=factory)
    return await runner.run_and_save(evalset, results_dir=results_dir)


def _print_run_summary(result: EvalRunResult, out_path: Path) -> None:
    print()
    print("=" * 72)
    print(f"Evalset: {result.evalset_name}")
    print(f"Cases:   {len(result.cases)}")
    print(f"Judge:   {result.judge_model}")
    print(f"Output:  {out_path}")
    print("-" * 72)
    if not result.metric_averages:
        print("(no metrics produced — check evalset expectations)")
    else:
        for metric, avg in sorted(result.metric_averages.items()):
            print(f"  {metric:42s}  {avg:.3f}")
    print("=" * 72)


async def _cmd_run(args: argparse.Namespace) -> int:
    config_dir = args.config or os.environ.get("GCLAW_CONFIG_DIR") or "."
    results_dir = args.results_dir
    Path(results_dir).mkdir(parents=True, exist_ok=True)

    factory = _build_minimal_factory(config_dir)

    targets: list[str] = []
    if args.all:
        targets = sorted(
            glob.glob(os.path.join(args.evalsets_dir, "*.json"))
        )
        if not targets:
            print(
                f"No evalsets found in {args.evalsets_dir}", file=sys.stderr
            )
            return 1
    else:
        targets = [args.evalset]

    rc = 0
    for target in targets:
        try:
            result, out_path = await _run_evalset_path(
                target, factory, results_dir
            )
        except Exception as e:
            logger.error("evalset %s failed to run: %s", target, e)
            rc = 1
            continue
        _print_run_summary(result, out_path)
    return rc


# ── `compare` subcommand ──────────────────────────────────────────────────


def _diff_results(
    baseline: EvalRunResult, candidate: EvalRunResult
) -> tuple[list[dict[str, Any]], float]:
    """Per-case metric deltas + the worst regression observed.

    Returns ``(rows, worst_regression)``. ``worst_regression`` is the
    largest single ``baseline - candidate`` delta (positive = the
    candidate is worse). ``rows`` is one entry per case, each carrying
    a per-metric delta map.
    """
    base_by_id = {c.case_id: c for c in baseline.cases}
    cand_by_id = {c.case_id: c for c in candidate.cases}

    rows: list[dict[str, Any]] = []
    worst = 0.0
    for case_id in sorted(set(base_by_id) | set(cand_by_id)):
        base_case = base_by_id.get(case_id)
        cand_case = cand_by_id.get(case_id)
        base_map = base_case.metric_map if base_case else {}
        cand_map = cand_case.metric_map if cand_case else {}
        deltas: dict[str, float] = {}
        for metric in sorted(set(base_map) | set(cand_map)):
            base_score = base_map.get(metric, 0.0)
            cand_score = cand_map.get(metric, 0.0)
            delta = cand_score - base_score
            deltas[metric] = delta
            regression = -delta  # positive when candidate is worse
            if regression > worst:
                worst = regression
        rows.append({
            "case_id": case_id,
            "deltas": deltas,
            "in_baseline": base_case is not None,
            "in_candidate": cand_case is not None,
        })
    return rows, worst


def _print_compare(
    rows: list[dict[str, Any]],
    worst: float,
    threshold: float,
    *,
    baseline_name: str,
    candidate_name: str,
) -> None:
    print()
    print("=" * 72)
    print(f"Compare: {baseline_name}  vs  {candidate_name}")
    print(f"Regression threshold: -{threshold:.3f}")
    print("-" * 72)
    for row in rows:
        case_id = row["case_id"]
        if not row["in_baseline"]:
            print(f"  [NEW]   {case_id}")
        elif not row["in_candidate"]:
            print(f"  [GONE]  {case_id}")
        for metric, delta in row["deltas"].items():
            sign = "+" if delta >= 0 else ""
            tag = " "
            if delta <= -threshold:
                tag = "!"
            print(f"  {tag} {case_id:40s} {metric:42s} {sign}{delta:.3f}")
    print("-" * 72)
    print(f"Worst regression: -{worst:.3f}")
    print("=" * 72)


def _cmd_compare(args: argparse.Namespace) -> int:
    baseline = EvalRunResult.from_json(args.baseline)
    candidate = EvalRunResult.from_json(args.candidate)
    rows, worst = _diff_results(baseline, candidate)
    _print_compare(
        rows,
        worst,
        args.threshold,
        baseline_name=Path(args.baseline).name,
        candidate_name=Path(args.candidate).name,
    )
    if worst > args.threshold:
        return 2
    return 0


# ── arg parser ────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gclaw-eval",
        description="Run gclaw evalsets (ADR-0005).",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="Run one or all evalsets.")
    target = run.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "--evalset", help="Path to a single evalset JSON file."
    )
    target.add_argument(
        "--all",
        action="store_true",
        help="Run every evalset in --evalsets-dir.",
    )
    run.add_argument(
        "--evalsets-dir",
        default=DEFAULT_EVALSETS_DIR,
        help=f"Directory of evalset JSONs (default: {DEFAULT_EVALSETS_DIR}).",
    )
    run.add_argument(
        "--results-dir",
        default=DEFAULT_RESULTS_DIR,
        help=f"Where to write result JSONs (default: {DEFAULT_RESULTS_DIR}).",
    )
    run.add_argument(
        "--config",
        default=None,
        help=(
            "Path to the gclaw config directory containing agents/ and "
            "soul/. Defaults to $GCLAW_CONFIG_DIR or the current directory."
        ),
    )
    run.set_defaults(func=lambda a: asyncio.run(_cmd_run(a)))

    cmp = sub.add_parser(
        "compare",
        help="Diff two evalset result files; non-zero exit on regression.",
    )
    cmp.add_argument("baseline", help="Baseline result JSON path.")
    cmp.add_argument("candidate", help="Candidate result JSON path.")
    cmp.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_REGRESSION_THRESHOLD,
        help=(
            "Maximum tolerated drop in any per-case metric "
            f"(default: {DEFAULT_REGRESSION_THRESHOLD})."
        ),
    )
    cmp.set_defaults(func=_cmd_compare)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level))
    rc = args.func(args)
    if isinstance(rc, int):
        return rc
    return 0


def _entry() -> None:  # pragma: no cover — pyproject script shim
    sys.exit(main())


if __name__ == "__main__":  # pragma: no cover
    _entry()
