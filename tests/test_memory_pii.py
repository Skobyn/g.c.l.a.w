"""Tests for the PII scrubber used before Memory Bank ingestion."""

from __future__ import annotations

import pytest

from gclaw.memory.pii import scrub_pii


def test_empty_input_no_op():
    scrubbed, report = scrub_pii("")
    assert scrubbed == ""
    assert report == {}


def test_plain_text_unchanged():
    text = "Let's talk about the quarterly roadmap."
    scrubbed, report = scrub_pii(text)
    assert scrubbed == text
    assert report == {}


def test_redacts_email():
    scrubbed, report = scrub_pii("ping sam@example.com when ready")
    assert "[REDACTED_EMAIL]" in scrubbed
    assert "sam@example.com" not in scrubbed
    assert report == {"email": 1}


def test_redacts_openai_api_key():
    key = "sk-abcdEFGH1234567890xyzxyzxyz"
    scrubbed, report = scrub_pii(f"token is {key}")
    assert "[REDACTED_API_KEY]" in scrubbed
    assert key not in scrubbed
    assert report.get("api_key") == 1


def test_redacts_anthropic_style_key():
    key = "sk-ant-api03-abc_def-GHIjkl123456789"
    scrubbed, _ = scrub_pii(f"auth: {key}")
    assert "[REDACTED_API_KEY]" in scrubbed
    assert key not in scrubbed


def test_redacts_aws_access_key():
    scrubbed, report = scrub_pii("cred: AKIAIOSFODNN7EXAMPLE")
    assert "[REDACTED_AWS_KEY]" in scrubbed
    assert "AKIAIOSFODNN7EXAMPLE" not in scrubbed
    assert report.get("aws_key") == 1


def test_redacts_jwt():
    jwt = (
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0."
        "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )
    scrubbed, report = scrub_pii(f"got token {jwt} from auth")
    assert "[REDACTED_JWT]" in scrubbed
    assert jwt not in scrubbed
    assert report.get("jwt") == 1


def test_redacts_private_key_block():
    pem = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEpAIBAAKCAQEAlorem ipsum dolor sit amet\n"
        "-----END RSA PRIVATE KEY-----"
    )
    scrubbed, report = scrub_pii(f"here is the key:\n{pem}\nend")
    assert "[REDACTED_PRIVATE_KEY]" in scrubbed
    assert "MIIEpAIBAAKCAQEA" not in scrubbed
    assert report.get("private_key") == 1


def test_redacts_ssn():
    scrubbed, report = scrub_pii("my ssn is 123-45-6789 please delete")
    assert "[REDACTED_SSN]" in scrubbed
    assert "123-45-6789" not in scrubbed
    assert report.get("ssn") == 1


def test_redacts_credit_card():
    scrubbed, report = scrub_pii("charge 4111-1111-1111-1111 for the order")
    assert "[REDACTED_CREDIT_CARD]" in scrubbed
    assert "4111" not in scrubbed
    assert report.get("credit_card") == 1


def test_redacts_us_phone():
    scrubbed, report = scrub_pii("call me at 415-555-0123 tomorrow")
    assert "[REDACTED_PHONE]" in scrubbed
    assert "415-555-0123" not in scrubbed
    assert report.get("phone") == 1


def test_redacts_e164_phone_with_country_code():
    scrubbed, report = scrub_pii("international: +1 (415) 555-0199")
    assert "[REDACTED_PHONE]" in scrubbed
    assert report.get("phone") == 1


def test_multiple_categories_in_one_pass():
    text = (
        "email me at sam@example.com with token sk-abc12345678901234567890 "
        "my phone is 555-123-4567"
    )
    scrubbed, report = scrub_pii(text)
    assert "[REDACTED_EMAIL]" in scrubbed
    assert "[REDACTED_API_KEY]" in scrubbed
    assert "[REDACTED_PHONE]" in scrubbed
    assert report == {"email": 1, "api_key": 1, "phone": 1}


def test_report_counts_duplicates():
    text = "write to a@b.co and c@d.co"
    _, report = scrub_pii(text)
    assert report == {"email": 2}


def test_does_not_mutate_input():
    text = "email: sam@example.com"
    original = text
    scrub_pii(text)
    assert text == original


def test_non_pii_at_sign_in_code_context():
    """Decorator syntax should not be redacted — the email pattern
    requires a proper TLD after the domain."""
    text = "@property\ndef foo(self): return 1"
    scrubbed, report = scrub_pii(text)
    assert "@property" in scrubbed
    assert "email" not in report
