"""Tool governance — permission-gated tool access with audit logging."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

logger = logging.getLogger(__name__)


class ToolRisk(IntEnum):
    READ_ONLY = 1
    WRITE = 2
    SYSTEM = 3


@dataclass
class ToolGrant:
    tool_name: str
    risk: ToolRisk
    allowed_agents: list[str]
    requires_approval: bool = False


class ToolGovernor:
    def __init__(self, grants: list[ToolGrant]) -> None:
        self._grants: dict[str, ToolGrant] = {g.tool_name: g for g in grants}
        self.audit_log: list[dict[str, Any]] = []

    def is_allowed(self, tool_name: str, agent_name: str) -> bool:
        grant = self._grants.get(tool_name)
        if grant is None:
            return False
        if "*" in grant.allowed_agents:
            return True
        return agent_name in grant.allowed_agents

    def requires_approval(self, tool_name: str) -> bool:
        grant = self._grants.get(tool_name)
        if grant is None:
            return False
        return grant.requires_approval

    def get_allowed_tools(self, agent_name: str) -> list[ToolGrant]:
        return [
            g
            for g in self._grants.values()
            if "*" in g.allowed_agents or agent_name in g.allowed_agents
        ]

    def check_and_log(self, tool_name: str, agent_name: str) -> bool:
        allowed = self.is_allowed(tool_name, agent_name)
        entry = {
            "tool": tool_name,
            "agent": agent_name,
            "allowed": allowed,
            "risk": self._grants[tool_name].risk.name if tool_name in self._grants else "UNKNOWN",
        }
        self.audit_log.append(entry)

        if not allowed:
            logger.warning(
                "Tool access DENIED: agent=%s tool=%s",
                agent_name,
                tool_name,
            )
        return allowed
