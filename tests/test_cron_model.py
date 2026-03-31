"""Tests for cron model."""

import pytest
from datetime import datetime, timezone

from gclaw.models.cron import (
    Cron,
    CronMode,
    CronStatus,
)


def test_create_minimal_cron():
    cron = Cron(
        title="Morning briefing",
        schedule="0 8 * * *",
        assignee="workspace-mgr",
    )
    assert cron.title == "Morning briefing"
    assert cron.schedule == "0 8 * * *"
    assert cron.assignee == "workspace-mgr"
    assert cron.mode == CronMode.TODO
    assert cron.status == CronStatus.ACTIVE
    assert cron.id.startswith("cron_")
    assert cron.created_at is not None


def test_create_auto_cron():
    cron = Cron(
        title="Inbox triage",
        schedule="*/30 * * * *",
        assignee="workspace-mgr",
        mode=CronMode.AUTO,
        description="Check and categorize new emails",
        task_priority="high",
    )
    assert cron.mode == CronMode.AUTO
    assert cron.description == "Check and categorize new emails"
    assert cron.task_priority == "high"


def test_create_paused_cron():
    cron = Cron(
        title="Weekly report",
        schedule="0 17 * * FRI",
        assignee="research-mgr",
        status=CronStatus.PAUSED,
    )
    assert cron.status == CronStatus.PAUSED


def test_cron_to_firestore_dict():
    cron = Cron(
        title="Test cron",
        schedule="0 9 * * *",
        assignee="dev-mgr",
    )
    d = cron.to_firestore_dict()
    assert d["title"] == "Test cron"
    assert d["schedule"] == "0 9 * * *"
    assert d["assignee"] == "dev-mgr"
    assert "id" not in d


def test_cron_from_firestore_dict():
    now = datetime.now(timezone.utc)
    d = {
        "title": "From Firestore",
        "description": "A cron from the DB",
        "schedule": "0 8 * * MON",
        "mode": "auto",
        "status": "active",
        "assignee": "workspace-mgr",
        "task_priority": "medium",
        "last_run": now,
        "next_run": now,
        "created_at": now,
        "updated_at": now,
    }
    cron = Cron.from_firestore_dict("cron_abc", d)
    assert cron.id == "cron_abc"
    assert cron.mode == CronMode.AUTO
    assert cron.status == CronStatus.ACTIVE
    assert cron.last_run == now


def test_cron_record_run():
    cron = Cron(
        title="Test",
        schedule="0 9 * * *",
        assignee="dev-mgr",
    )
    assert cron.last_run is None
    updated = cron.record_run()
    assert updated.last_run is not None
    assert updated.updated_at >= cron.updated_at
