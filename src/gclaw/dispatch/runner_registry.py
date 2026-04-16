"""Registry of per-agent AgentRunner instances.

The chat endpoint takes an optional ``agent_name`` so the user can talk
directly to any agent (orchestrator, a manager, or a leaf specialist).
Each agent needs its own ``AgentRunner`` because each wraps a distinct
ADK ``LlmAgent`` (different tools, soul, model, sub-agents).

Rather than building N runners up front in ``main.py`` — most of which
will never be used in a given process lifetime — the registry builds
lazily on first access via an injected builder callable. The builder
receives the agent name and is expected to return a fully wired
``AgentRunner`` sharing the same session/memory/board/session-store/
usage-recorder dependencies as the default (orchestrator) runner.

Session scoping is handled by the caller: the chat endpoint appends the
non-default agent name to the session_id so different agents don't
stomp on each other's ADK session state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from gclaw.dispatch.runner import AgentRunner


class AgentRunnerRegistry:
    """Holds one AgentRunner per agent name.

    Lazy: builds on first ``get()`` call using the injected builder.
    Subsequent calls return the cached instance.
    """

    def __init__(
        self,
        *,
        default_agent: str = "orchestrator",
        builder: Callable[[str], "AgentRunner"],
    ) -> None:
        self._default = default_agent
        self._builder = builder
        self._runners: dict[str, "AgentRunner"] = {}

    def get(self, agent_name: str | None = None) -> "AgentRunner":
        """Return the runner for ``agent_name`` (default when None/empty).

        Builds on first access. Raises whatever the builder raises on
        bad agent names; caller decides whether to swallow or surface.
        """
        name = agent_name or self._default
        if name not in self._runners:
            self._runners[name] = self._builder(name)
        return self._runners[name]

    def register(self, agent_name: str, runner: "AgentRunner") -> None:
        """Pre-seed the registry with an already-built runner.

        Used by ``main.py`` to register the shared orchestrator runner
        under ``default_agent`` so it's reused byte-for-byte (same
        fallback chain, same heartbeat wiring) rather than being
        rebuilt on first chat hit.
        """
        self._runners[agent_name] = runner

    def default_agent(self) -> str:
        return self._default

    def loaded(self) -> list[str]:
        """Names of runners that have actually been built so far."""
        return sorted(self._runners.keys())
