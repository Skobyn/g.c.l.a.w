"""Tests for workflow validator agents."""

from unittest.mock import MagicMock

import pytest

from gclaw.agents.workflows.validators import ValidateCommitMsg


@pytest.fixture
def validate_agent():
    return ValidateCommitMsg(name="validate_commit_msg")


@pytest.mark.asyncio
async def test_validate_pass_yields_approved_draft(validate_agent):
    ctx = MagicMock()
    ctx.session.state = {
        "review_status": "pass",
        "commit_draft": "feat: add new widget",
    }

    events = [e async for e in validate_agent._run_async_impl(ctx)]
    assert len(events) == 1

    text = events[0].content.parts[0].text
    assert "approved" in text.lower()
    assert "feat: add new widget" in text


@pytest.mark.asyncio
async def test_validate_fail_yields_rejection_with_reason(validate_agent):
    ctx = MagicMock()
    ctx.session.state = {
        "review_status": "fail: subject line too long",
        "commit_draft": "feat: this subject line is way too long and breaks conventions",
    }

    events = [e async for e in validate_agent._run_async_impl(ctx)]
    assert len(events) == 1

    text = events[0].content.parts[0].text
    assert "rejected" in text.lower()
    assert "subject line too long" in text
    assert "this subject line is way too long" in text


@pytest.mark.asyncio
async def test_validate_missing_state_yields_rejection(validate_agent):
    ctx = MagicMock()
    ctx.session.state = {}

    events = [e async for e in validate_agent._run_async_impl(ctx)]
    assert len(events) == 1

    text = events[0].content.parts[0].text
    assert "rejected" in text.lower()


@pytest.mark.asyncio
async def test_validate_fail_without_prefix(validate_agent):
    ctx = MagicMock()
    ctx.session.state = {
        "review_status": "FAIL",
        "commit_draft": "x",
    }

    events = [e async for e in validate_agent._run_async_impl(ctx)]
    text = events[0].content.parts[0].text
    assert "rejected" in text.lower()
