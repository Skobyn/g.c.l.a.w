"""Tests for the regex-based redaction module (ADR-0004 Phase 1)."""

from __future__ import annotations

import copy

import pytest

from gclaw.observability.redaction import redact, redact_object


# ── redact() — per-pattern positive + negative cases ────────────────


def test_redact_email_positive():
    out = redact("contact me at scott@example.com please")
    assert "<REDACTED:email>" in out
    assert "scott@example.com" not in out


def test_redact_email_negative():
    # Bare word with @ but no domain shouldn't match.
    assert "@nodomain" in redact("ping @nodomain ok")


def test_redact_phone_positive():
    out = redact("call +1 415-555-1234 tonight")
    assert "<REDACTED:phone>" in out
    assert "415" not in out


def test_redact_phone_negative():
    # 5-digit number is too short.
    assert redact("zip 94110") == "zip 94110"


def test_redact_gcp_secret_ref_positive():
    raw = "secret: projects/my-proj/secrets/my-key/versions/3"
    out = redact(raw)
    assert "<REDACTED:gcp_secret_ref>" in out
    assert "my-key" not in out


def test_redact_gcp_secret_ref_latest():
    raw = "projects/p/secrets/abc/versions/latest"
    assert "<REDACTED:gcp_secret_ref>" in redact(raw)


def test_redact_gcp_secret_ref_negative():
    # Looks like a project path but not the right shape.
    assert redact("projects/foo/topics/bar") == "projects/foo/topics/bar"


def test_redact_aws_key_positive():
    out = redact("AKIAIOSFODNN7EXAMPLE is the key")
    assert "<REDACTED:aws_access_key>" in out


def test_redact_aws_key_negative():
    # Wrong prefix.
    assert redact("BKIA1234567890ABCDEF") == "BKIA1234567890ABCDEF"


def test_redact_github_token_positive():
    out = redact("token=ghp_" + "A" * 36 + " ok")
    assert "<REDACTED:github_token>" in out


def test_redact_github_token_negative():
    assert redact("ghp_short") == "ghp_short"


def test_redact_anthropic_oauth_positive():
    out = redact("auth: sk-ant-oat01-deadbeef-XYZ ok")
    assert "<REDACTED:anthropic_oauth>" in out


def test_redact_anthropic_oauth_negative():
    # Must have the digits before the dash.
    assert "sk-ant-oat" in redact("sk-ant-oat-no-digits")


def test_redact_anthropic_api_positive():
    out = redact("X-API-Key: sk-ant-api03-AbCdEf-GhIjKl_MnO")
    assert "<REDACTED:anthropic_api>" in out


def test_redact_openai_positive():
    out = redact("OPENAI=sk-proj-" + "a" * 32)
    assert "<REDACTED:openai_key>" in out


def test_redact_openai_negative():
    # Too short.
    assert redact("sk-short") == "sk-short"


def test_redact_jwt_positive():
    jwt = "eyJabc123.eyJabc456.signature_part_42"
    out = redact(f"Bearer {jwt}")
    assert "<REDACTED:jwt>" in out
    assert jwt not in out


def test_redact_jwt_negative():
    # Only two segments.
    assert redact("eyJabc.eyJdef") == "eyJabc.eyJdef"


# ── empty / None / non-string handling ──────────────────────────────


def test_redact_empty_string():
    assert redact("") == ""


def test_redact_none_returns_empty():
    assert redact(None) == ""


def test_redact_non_string_coerces():
    # Passing a number through should not crash. Plain digits aren't
    # a sensitive pattern, so the coerced string passes through.
    assert redact(12345) == "12345"


# ── redact_object — recursion ───────────────────────────────────────


def test_redact_object_recurses_through_dict():
    obj = {
        "user": "scott@example.com",
        "phone": "+1 415-555-1234",
        "count": 7,
    }
    out = redact_object(obj)
    assert "<REDACTED:email>" in out["user"]
    assert "<REDACTED:phone>" in out["phone"]
    assert out["count"] == 7


def test_redact_object_recurses_through_list():
    out = redact_object(["scott@example.com", "ok", 1])
    assert "<REDACTED:email>" in out[0]
    assert out[1] == "ok"
    assert out[2] == 1


def test_redact_object_recurses_through_nested():
    obj = {
        "messages": [
            {"role": "user", "content": "ping scott@example.com"},
            {"role": "assistant", "content": "no PII here"},
        ],
        "meta": {"keys": ["AKIAIOSFODNN7EXAMPLE", "safe"]},
    }
    out = redact_object(obj)
    assert "<REDACTED:email>" in out["messages"][0]["content"]
    assert out["messages"][1]["content"] == "no PII here"
    assert "<REDACTED:aws_access_key>" in out["meta"]["keys"][0]
    assert out["meta"]["keys"][1] == "safe"


def test_redact_object_handles_tuple():
    out = redact_object(("scott@example.com", "safe"))
    assert isinstance(out, tuple)
    assert "<REDACTED:email>" in out[0]


def test_redact_object_does_not_mutate_input():
    obj = {
        "user": "scott@example.com",
        "messages": [{"content": "AKIAIOSFODNN7EXAMPLE"}],
    }
    snapshot = copy.deepcopy(obj)
    _ = redact_object(obj)
    assert obj == snapshot


def test_redact_object_handles_none_and_primitives():
    assert redact_object(None) is None
    assert redact_object(True) is True
    assert redact_object(0) == 0


@pytest.mark.parametrize(
    "value",
    [
        "no PII here",
        "just some normal text 12345",
        "",
    ],
)
def test_redact_passthrough_when_clean(value: str):
    assert redact(value) == value
