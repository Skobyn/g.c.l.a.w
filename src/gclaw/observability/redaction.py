"""Cheap regex-based PII / secret redaction.

Used by :mod:`gclaw.observability.prompt_log` to scrub prompts and
responses before they're written to GCS. Phase 1 from ADR-0004:
known patterns only, no LLM calls, no Cloud DLP. Replaces matches
with ``<REDACTED:type>`` so reviewers can see what kind of value was
removed without recovering it.

Patterns intentionally err on the side of false positives — losing
visibility on a prompt that mentioned an email address is far cheaper
than parking a real OpenAI key in a year-retained GCS object.

Pattern order matters: more specific provider key shapes run BEFORE
the generic OpenAI ``sk-…`` and JWT patterns so an Anthropic OAuth
token doesn't get caught by the OpenAI rule first.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# (label, compiled pattern). First match wins per scan.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # Provider-specific tokens — most specific first.
    ("anthropic_oauth", re.compile(r"sk-ant-oat\d+-[A-Za-z0-9_-]+")),
    ("anthropic_api", re.compile(r"sk-ant-api\d+-[A-Za-z0-9_-]+")),
    ("openai_key", re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}")),
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}")),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    # GCP Secret Manager resource references (versions/<num> or /latest).
    (
        "gcp_secret_ref",
        re.compile(
            r"projects/[^/\s]+/secrets/[^/\s]+/versions/(?:\d+|latest)"
        ),
    ),
    # JWTs — three base64url segments. Match before generic patterns
    # because the trailing segment can look like a long opaque token.
    (
        "jwt",
        re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
    ),
    # PII — emails + phone numbers.
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    (
        "phone",
        re.compile(r"\+?\d{1,3}[-\s]?\(?\d{3}\)?[-\s]?\d{3}[-\s]?\d{4}"),
    ),
)


def redact(text: str | None) -> str:
    """Return ``text`` with known sensitive patterns replaced.

    Empty / ``None`` input returns ``""``. Non-string input is coerced
    via ``str()`` to keep callers from having to type-check before
    redacting structured payloads.
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    if not text:
        return text
    for label, pat in _PATTERNS:
        text = pat.sub(f"<REDACTED:{label}>", text)
    return text


def redact_object(obj: Any) -> Any:
    """Recursively redact strings inside dicts, lists, and tuples.

    Returns a new structure — never mutates the input. Non-string
    leaf values (ints, bools, ``None``) pass through unchanged.
    """
    if isinstance(obj, str):
        return redact(obj)
    if isinstance(obj, dict):
        return {k: redact_object(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_object(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(redact_object(v) for v in obj)
    return obj
