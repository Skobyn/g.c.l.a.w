"""LLM-as-judge client used by the rubric/semantic metrics.

Wraps an ADK ``Runner`` so metrics can ask cheap one-shot questions of
a judge model without each metric having to rebuild the runner. Verdicts
are cached on the (input, response, rubric) tuple so the same judge
prompt asked twice in a single ``EvalRunner.run_evalset`` only burns
tokens once.

The judge contract is intentionally narrow: ask for a JSON blob with
``score`` (0..1 float) and ``rationale`` (str). Metrics convert
free-form rubrics into a judge prompt; the JudgeClient just runs it.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class JudgeVerdict:
    """Parsed judge response. ``score`` is clamped to [0.0, 1.0]."""

    score: float
    rationale: str = ""
    raw: str = ""


def _hash(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


# JSON looks like {"score": 0.8, "rationale": "..."} — be lenient about
# whitespace, surrounding prose, or markdown fences (the model often
# wraps its JSON in ```json ... ```).
_JSON_BLOCK_RE = re.compile(r"\{.*?\}", re.DOTALL)


def _parse_verdict(raw: str) -> JudgeVerdict:
    """Pull a JSON ``{score, rationale}`` out of the judge's reply.

    Falls back to a 0.0 verdict with the raw text as rationale if no
    parsable JSON can be found — that way a flaky judge produces a hard
    failure rather than a silent pass.
    """
    text = raw.strip()
    # Strip ```json fences if present.
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    candidates: list[str] = []
    if text.startswith("{"):
        candidates.append(text)
    candidates.extend(_JSON_BLOCK_RE.findall(text))

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        score = data.get("score")
        rationale = data.get("rationale") or data.get("reason") or ""
        if isinstance(score, (int, float)):
            clamped = max(0.0, min(1.0, float(score)))
            return JudgeVerdict(
                score=clamped,
                rationale=str(rationale),
                raw=raw,
            )

    logger.warning("judge: could not parse JSON verdict from %r", raw[:200])
    return JudgeVerdict(score=0.0, rationale=raw[:500], raw=raw)


class JudgeClient:
    """Cached judge-model wrapper.

    Two construction paths:

    - ``model_name`` only: the client lazily builds an ADK ``Runner`` with
      a bare ``LlmAgent`` the first time ``ask`` is called. Use this in
      production code paths.
    - ``ask_fn`` injected: callers (tests, custom judges) supply an
      async callable ``(prompt: str) -> str``. The client never touches
      ADK in that mode.
    """

    def __init__(
        self,
        model_name: str = "gemini-2.5-flash",
        *,
        ask_fn: Callable[[str], "asyncio.Future[str] | Any"] | None = None,
        app_name: str = "gclaw-eval-judge",
    ) -> None:
        self._model_name = model_name
        self._ask_fn = ask_fn
        self._app_name = app_name
        self._cache: dict[str, JudgeVerdict] = {}
        self._call_count = 0
        # Lazy ADK plumbing — only instantiated if ``ask_fn`` is None
        # AND the first call actually arrives.
        self._adk_runner: Any | None = None
        self._adk_session_id: str | None = None
        self._adk_user_id = "judge"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def call_count(self) -> int:
        """Number of judge calls that actually hit the model
        (i.e. cache misses)."""
        return self._call_count

    @property
    def cache_size(self) -> int:
        return len(self._cache)

    def cache_key(self, *, input_: str, response: str, rubric: str) -> str:
        return _hash(input_, response, rubric)

    async def ask(
        self,
        *,
        input_: str,
        response: str,
        rubric: str,
        prompt: str,
    ) -> JudgeVerdict:
        """Score ``response`` for ``input_`` against ``rubric``.

        ``prompt`` is the fully-rendered judge prompt; the metric is
        responsible for stitching together ``input_``/``response``/``rubric``
        into whatever instruction it wants the judge to follow. The
        client only owns caching and transport.
        """
        key = self.cache_key(input_=input_, response=response, rubric=rubric)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        raw = await self._invoke(prompt)
        verdict = _parse_verdict(raw)
        self._cache[key] = verdict
        self._call_count += 1
        return verdict

    # ── transport ──────────────────────────────────────────────────────

    async def _invoke(self, prompt: str) -> str:
        if self._ask_fn is not None:
            res = self._ask_fn(prompt)
            if asyncio.iscoroutine(res) or isinstance(res, asyncio.Future):
                return str(await res)
            return str(res)
        return await self._invoke_adk(prompt)

    async def _invoke_adk(self, prompt: str) -> str:
        runner = await self._ensure_adk_runner()
        session_id = f"judge-{uuid.uuid4().hex}"
        try:
            await runner.session_service.create_session(
                app_name=self._app_name,
                user_id=self._adk_user_id,
                session_id=session_id,
            )
        except Exception:
            # Some session services accept duplicate creates; others raise.
            # Either way we attempt to proceed.
            pass

        from google.genai import types

        content = types.Content(role="user", parts=[types.Part(text=prompt)])
        out_text = ""
        async for event in runner.run_async(
            user_id=self._adk_user_id,
            session_id=session_id,
            new_message=content,
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        out_text += part.text
        return out_text

    async def _ensure_adk_runner(self) -> Any:
        if self._adk_runner is not None:
            return self._adk_runner
        from google.adk.agents import LlmAgent
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService

        agent = LlmAgent(
            name="gclaw_eval_judge",
            model=self._model_name,
            instruction=(
                "You are a strict evaluation judge. Always reply with a single "
                "JSON object of the form "
                '{"score": <0..1 float>, "rationale": "<short reason>"}. '
                "No prose outside the JSON."
            ),
            description="Eval judge model used by gclaw-eval metrics.",
        )
        self._adk_runner = Runner(
            agent=agent,
            app_name=self._app_name,
            session_service=InMemorySessionService(),
        )
        return self._adk_runner
