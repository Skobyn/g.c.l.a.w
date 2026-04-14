"""Registry of per-agent HeartbeatService instances.

Each agent that opts into a heartbeat (via YAML frontmatter on its
``agents/<name>.md`` file) gets its own ``HeartbeatService`` wired with
the shared deps (board, memory, cron queue, runner). The registry gives
the scheduler loop and the admin routes a single place to look them up.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gclaw.heartbeat.config import HeartbeatConfig
    from gclaw.heartbeat.service import HeartbeatService


class HeartbeatRegistry:
    """Holds one HeartbeatService per agent that opted into heartbeat."""

    def __init__(self) -> None:
        self._services: dict[str, "HeartbeatService"] = {}
        self._configs: dict[str, "HeartbeatConfig"] = {}

    def register(
        self,
        agent_name: str,
        service: "HeartbeatService",
        config: "HeartbeatConfig",
    ) -> None:
        self._services[agent_name] = service
        self._configs[agent_name] = config

    def get(self, agent_name: str) -> "HeartbeatService | None":
        return self._services.get(agent_name)

    def get_config(self, agent_name: str) -> "HeartbeatConfig | None":
        return self._configs.get(agent_name)

    def all_agents(self) -> list[str]:
        return list(self._services.keys())

    def items(
        self,
    ) -> list[tuple[str, "HeartbeatService", "HeartbeatConfig"]]:
        return [
            (name, self._services[name], self._configs[name])
            for name in self._services
        ]
