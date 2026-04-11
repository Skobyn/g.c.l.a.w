"""CLI entry point: `python -m gclaw.eval`.

Builds the real GClaw app (via `main.build_app`), extracts the
live `AgentRunner`, runs the golden case set, prints a report, and
exits 0 on ≥80% pass rate or 1 otherwise.

Hits live Gemini. Costs real tokens. Run manually — not in CI.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from gclaw.eval.cases import GOLDEN_CASES
from gclaw.eval.runner import print_report, run_eval

logger = logging.getLogger("gclaw.eval")


PASS_RATE_THRESHOLD = 0.80


def _extract_runner(app):
    """Pull the AgentRunner out of a FastAPI app.

    The chat router stashes the runner at module-level in
    `gclaw.api.chat._runner` when `init_chat_router(runner)` is called
    from `create_app`. Reach for that rather than re-building the whole
    stack.
    """
    from gclaw.api import chat
    if chat._runner is None:
        raise RuntimeError(
            "chat._runner is None after build_app — the chat router was not "
            "initialised. This usually means create_app changed and no longer "
            "calls init_chat_router. Wire up a new accessor."
        )
    return chat._runner


async def _amain() -> int:
    logging.basicConfig(level=logging.WARNING)
    logger.setLevel(logging.INFO)

    from gclaw.main import build_app
    app = build_app()
    runner = _extract_runner(app)

    logger.info(
        "running %d golden eval cases against the live orchestrator",
        len(GOLDEN_CASES),
    )
    result = await run_eval(runner, GOLDEN_CASES)

    print_report(result)

    if result.pass_rate < PASS_RATE_THRESHOLD:
        logger.warning(
            "pass rate %.1f%% is below the %.0f%% threshold",
            result.pass_rate * 100,
            PASS_RATE_THRESHOLD * 100,
        )
        return 1
    return 0


def main() -> None:
    rc = asyncio.run(_amain())
    sys.exit(rc)


if __name__ == "__main__":
    main()
