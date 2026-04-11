"""Tests for tool governance and permission gating."""

import pytest
from gclaw.tools.governance import ToolRisk, ToolGrant, ToolGovernor


def test_tool_risk_ordering():
    assert ToolRisk.READ_ONLY.value < ToolRisk.WRITE.value
    assert ToolRisk.WRITE.value < ToolRisk.SYSTEM.value


def test_tool_grant():
    grant = ToolGrant(
        tool_name="gmail_send",
        risk=ToolRisk.WRITE,
        allowed_agents=["workspace-mgr", "comms-mgr"],
    )
    assert grant.tool_name == "gmail_send"
    assert "workspace-mgr" in grant.allowed_agents


def test_governor_allows_granted_agent():
    grants = [
        ToolGrant(
            tool_name="gmail_send",
            risk=ToolRisk.WRITE,
            allowed_agents=["workspace-mgr"],
        ),
    ]
    gov = ToolGovernor(grants=grants)
    assert gov.is_allowed("gmail_send", "workspace-mgr") is True


def test_governor_blocks_ungated_agent():
    grants = [
        ToolGrant(
            tool_name="gmail_send",
            risk=ToolRisk.WRITE,
            allowed_agents=["workspace-mgr"],
        ),
    ]
    gov = ToolGovernor(grants=grants)
    assert gov.is_allowed("gmail_send", "research-mgr") is False


def test_governor_unknown_tool_denied():
    gov = ToolGovernor(grants=[])
    assert gov.is_allowed("unknown_tool", "orchestrator") is False


def test_governor_read_only_allowed_for_all():
    grants = [
        ToolGrant(
            tool_name="list_board_tasks",
            risk=ToolRisk.READ_ONLY,
            allowed_agents=["*"],
        ),
    ]
    gov = ToolGovernor(grants=grants)
    assert gov.is_allowed("list_board_tasks", "any-agent") is True


def test_governor_system_requires_approval():
    grants = [
        ToolGrant(
            tool_name="delete_user_data",
            risk=ToolRisk.SYSTEM,
            allowed_agents=["orchestrator"],
            requires_approval=True,
        ),
    ]
    gov = ToolGovernor(grants=grants)
    assert gov.requires_approval("delete_user_data") is True
    assert gov.requires_approval("unknown_tool") is False


def test_governor_get_tools_for_agent():
    grants = [
        ToolGrant(tool_name="gmail_send", risk=ToolRisk.WRITE, allowed_agents=["workspace-mgr"]),
        ToolGrant(tool_name="gmail_read", risk=ToolRisk.READ_ONLY, allowed_agents=["*"]),
        ToolGrant(tool_name="github_push", risk=ToolRisk.WRITE, allowed_agents=["dev-mgr"]),
    ]
    gov = ToolGovernor(grants=grants)
    tools = gov.get_allowed_tools("workspace-mgr")
    tool_names = [t.tool_name for t in tools]
    assert "gmail_send" in tool_names
    assert "gmail_read" in tool_names
    assert "github_push" not in tool_names


def test_audit_log():
    grants = [
        ToolGrant(tool_name="gmail_send", risk=ToolRisk.WRITE, allowed_agents=["workspace-mgr"]),
    ]
    gov = ToolGovernor(grants=grants)
    gov.check_and_log("gmail_send", "workspace-mgr")
    gov.check_and_log("gmail_send", "research-mgr")
    assert len(gov.audit_log) == 2
    assert gov.audit_log[0]["allowed"] is True
    assert gov.audit_log[1]["allowed"] is False
