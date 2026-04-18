"""Built-in validators for the guardrail pipeline.

These are intentionally lightweight (no external deps) so the guardrail
path doesn't drag in a spaCy pipeline or a local classifier at import
time. The :class:`Validator` protocol is compatible with the
``guardrails-ai`` package's validator shape; swapping in Guardrails AI
validators or Patronus/Galileo scorers later is a drop-in replacement.

Registered validators today:
  * :class:`PiiValidator`       — regex sweep for emails, phones,
                                   credit-card-ish, and SSN-ish strings.
  * :class:`ToxicityValidator`  — keyword block-list (stub — swap in a
                                   proper classifier like Llama-Guard
                                   when we need it).
  * :class:`LengthValidator`    — guard against runaway completions.
  * :class:`GroundednessValidator` — noop scaffold; set with an async
                                   judge function (Gemini LLM-as-judge)
                                   in config for RAG outputs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

from gclaw.guardrails.models import Outcome, Violation


class Validator(Protocol):
    """Async-callable validator. Returns None on pass, Violation otherwise."""

    name: str

    async def check(
        self, text: str, context: dict[str, Any] | None = None
    ) -> Violation | None:
        ...  # pragma: no cover


# ── PII ────────────────────────────────────────────────────────────────

_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
# Not exhaustive — catches US +E.164 and common (xxx) xxx-xxxx shapes.
# `\b` can't sit between a space and a `(`, so anchor with a negative-
# lookbehind for word chars / digits instead.
_PHONE_RE = re.compile(
    r"(?<![\w\d])(?:\+?1[\s\-\.]?)?"
    r"(?:\(\d{3}\)|\d{3})[\s\-\.]?\d{3}[\s\-\.]?\d{4}(?!\d)"
)
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
# Luhn-agnostic 13-16 digit run with optional grouping.
_CC_RE = re.compile(
    r"\b(?:\d[ \-]?){13,16}\b"
)


@dataclass
class PiiValidator:
    """Flags emails, phones, SSNs, and credit-card-shaped digits.

    ``outcome_for_detect`` controls whether matches warn or block.
    """

    name: str = "pii"
    outcome_for_detect: Outcome = Outcome.WARN

    async def check(
        self, text: str, context: dict[str, Any] | None = None
    ) -> Violation | None:
        hits: dict[str, list[str]] = {}
        for kind, pattern in (
            ("email", _EMAIL_RE),
            ("phone", _PHONE_RE),
            ("ssn", _SSN_RE),
            ("credit_card", _CC_RE),
        ):
            matches = pattern.findall(text or "")
            if matches:
                hits[kind] = matches[:5]
        if not hits:
            return None
        return Violation(
            validator=self.name,
            outcome=self.outcome_for_detect,
            message=f"PII detected: {', '.join(hits.keys())}",
            details={"matches": hits},
        )


# ── Toxicity (stub) ────────────────────────────────────────────────────

_DEFAULT_BAD_WORDS = frozenset(
    {
        # Minimal, illustrative. Real deployments should swap in a proper
        # classifier via a custom Validator implementation.
        "kill yourself",
        "i will hurt you",
    }
)


@dataclass
class ToxicityValidator:
    name: str = "toxicity"
    bad_words: frozenset[str] = _DEFAULT_BAD_WORDS
    outcome_for_detect: Outcome = Outcome.BLOCK

    async def check(
        self, text: str, context: dict[str, Any] | None = None
    ) -> Violation | None:
        lower = (text or "").lower()
        hits = [w for w in self.bad_words if w in lower]
        if not hits:
            return None
        return Violation(
            validator=self.name,
            outcome=self.outcome_for_detect,
            message=f"toxic phrase detected ({len(hits)})",
            details={"matches": hits},
        )


# ── Length ─────────────────────────────────────────────────────────────


@dataclass
class LengthValidator:
    name: str = "length"
    max_chars: int = 64_000
    outcome_for_exceed: Outcome = Outcome.WARN

    async def check(
        self, text: str, context: dict[str, Any] | None = None
    ) -> Violation | None:
        n = len(text or "")
        if n <= self.max_chars:
            return None
        return Violation(
            validator=self.name,
            outcome=self.outcome_for_exceed,
            message=f"output length {n} exceeded cap {self.max_chars}",
            details={"length": n, "max": self.max_chars},
        )


# ── Groundedness (pluggable judge) ─────────────────────────────────────


@dataclass
class GroundednessValidator:
    """Judges whether ``text`` is entailed by the retrieved context.

    ``judge`` receives ``(text, context_texts)`` and should return a
    float in [0, 1] where 1.0 is fully grounded. Below ``threshold``
    produces a violation with ``outcome_for_low``.

    Plug in Gemini LLM-as-judge (or Vectara HHEM / Galileo Lynx) as the
    ``judge`` callable; not built-in to avoid a hard Gemini dep here.
    """

    name: str = "groundedness"
    judge: Callable[[str, list[str]], Awaitable[float]] | None = None
    threshold: float = 0.6
    outcome_for_low: Outcome = Outcome.WARN

    async def check(
        self, text: str, context: dict[str, Any] | None = None
    ) -> Violation | None:
        if self.judge is None:
            return None
        contexts = _extract_context_texts(context)
        if not contexts:
            return None
        try:
            score = float(await self.judge(text, contexts))
        except Exception as e:  # noqa: BLE001
            return Violation(
                validator=self.name,
                outcome=Outcome.WARN,
                message=f"judge raised: {e!r}",
                details={"error": str(e)},
            )
        if score >= self.threshold:
            return None
        return Violation(
            validator=self.name,
            outcome=self.outcome_for_low,
            message=f"groundedness score {score:.2f} < {self.threshold:.2f}",
            details={"score": score, "threshold": self.threshold},
        )


def _extract_context_texts(
    context: dict[str, Any] | None,
) -> list[str]:
    if not context:
        return []
    raw = context.get("retrieval") or context.get("contexts") or []
    if isinstance(raw, str):
        return [raw]
    return [str(x) for x in raw]
