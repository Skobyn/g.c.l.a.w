"""Factory for building ADK agents from config files."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from google.adk.agents import LlmAgent

from gclaw.config.loader import ConfigLoader

if TYPE_CHECKING:
    from gclaw.routing.router import ModelRouter


class AgentFactory:
    """Creates ADK LlmAgent instances from soul/agent.md config files."""

    def __init__(
        self,
        loader: ConfigLoader,
        default_model: str = "gemini-2.5-flash",
        model_router: ModelRouter | None = None,
    ) -> None:
        self._loader = loader
        self._default_model = default_model
        self._router = model_router

    def build(
        self,
        agent_name: str,
        soul_overlay: str | None = None,
        memories: list[str] | None = None,
        tools: list[Any] | None = None,
        sub_agents: list[LlmAgent] | None = None,
        model: str | None = None,
        description: str | None = None,
    ) -> LlmAgent:
        instruction = self._loader.build_system_prompt(
            agent_name=agent_name,
            soul_base="base",
            soul_overlay=soul_overlay,
            memories=memories,
        )

        # Model resolution priority: explicit > router > default
        resolved_model = model
        if resolved_model is None and self._router is not None:
            resolved_model = self._router.resolve_for_agent(agent_name)
        if resolved_model is None:
            resolved_model = self._default_model

        safe_name = agent_name.replace("-", "_")
        return LlmAgent(
            name=safe_name,
            model=resolved_model,
            instruction=instruction,
            description=description or f"GClaw agent: {agent_name}",
            tools=tools or [],
            sub_agents=sub_agents or [],
        )
