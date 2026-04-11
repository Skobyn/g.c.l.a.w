"""PII scrubbing for memory ingestion.

Before GClaw sends conversation text to Memory Bank for extraction,
we run a regex-based scrubber that redacts common PII categories:
emails, phone numbers, credit cards, SSN-shaped numbers, API keys,
and JWT tokens.

This is a **minimum viable** pass — regex-only, no entity recognition,
no address or name detection. It catches the compliance-critical
failure modes (credentials in chat logs, financial data, government
IDs) without false-positive noise. For richer PII detection, consider
Google Cloud DLP API as a follow-up.

Usage::

    from gclaw.memory.pii import scrub_pii

    clean, report = scrub_pii("email me at sam@example.com")
    # clean == "email me at [REDACTED_EMAIL]"
    # report == {"email": 1}

The scrubber never raises on malformed input and never mutates the
original string.
"""

from __future__ import annotations

import re
from collections import Counter


_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    # OpenAI / Anthropic / generic API keys starting with `sk-` or `pk-`.
    # Intentionally broad — catches secret prefixes commonly pasted by
    # users demonstrating a tool or sharing an error message.
    (
        "api_key",
        re.compile(r"\b(?:sk|pk)-[A-Za-z0-9_\-]{16,}\b"),
        "[REDACTED_API_KEY]",
    ),
    # AWS access key IDs.
    (
        "aws_key",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "[REDACTED_AWS_KEY]",
    ),
    # Google Cloud OAuth refresh tokens look like 1// followed by
    # base64url. Rough guard.
    (
        "google_token",
        re.compile(r"\b1//[A-Za-z0-9_\-]{20,}\b"),
        "[REDACTED_GOOGLE_TOKEN]",
    ),
    # JWT — three base64url segments separated by dots. Must be long
    # enough to be plausibly a real token.
    (
        "jwt",
        re.compile(
            r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b"
        ),
        "[REDACTED_JWT]",
    ),
    # Private key blocks (literal PEM headers).
    (
        "private_key",
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"
        ),
        "[REDACTED_PRIVATE_KEY]",
    ),
    # Credit card numbers — 13 to 19 digits, optionally separated by
    # spaces or dashes in groups of 4. Does not validate Luhn
    # checksums, so this may redact long non-card numbers; the
    # false-positive risk is worth the safety.
    (
        "credit_card",
        re.compile(r"\b(?:\d[ \-]?){13,19}\b"),
        "[REDACTED_CREDIT_CARD]",
    ),
    # US SSN — 3-2-4 digit groups with dashes required to reduce FP.
    (
        "ssn",
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "[REDACTED_SSN]",
    ),
    # E.164-ish and common US phone patterns — must start with a
    # non-digit boundary and have at least 10 digits total. The
    # credit-card pattern will catch larger number blobs first.
    (
        "phone",
        re.compile(
            r"(?<!\d)(?:\+?1[ \-\.]?)?\(?\d{3}\)?[ \-\.]\d{3}[ \-\.]\d{4}(?!\d)"
        ),
        "[REDACTED_PHONE]",
    ),
    # Email addresses — keep the pattern narrow so we don't eat
    # every "@" in a conversation. Runs after api_key / jwt so we
    # don't mis-redact those as emails.
    (
        "email",
        re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
        "[REDACTED_EMAIL]",
    ),
]


def scrub_pii(text: str) -> tuple[str, dict[str, int]]:
    """Redact common PII categories in `text`.

    Args:
        text: The input string (typically conversation_text passed
            to Memory Bank for extraction).

    Returns:
        (scrubbed_text, redaction_report). `redaction_report` is a
        dict mapping category name (`"email"`, `"api_key"`, etc.) to
        the number of redactions of that category. Categories with
        zero redactions are omitted. The original `text` is never
        mutated.
    """
    if not text:
        return text, {}

    scrubbed = text
    report: Counter[str] = Counter()

    for category, pattern, replacement in _PATTERNS:
        def _sub(match: re.Match[str], _cat: str = category, _rep: str = replacement) -> str:
            report[_cat] += 1
            return _rep

        scrubbed = pattern.sub(_sub, scrubbed)

    return scrubbed, dict(report)
