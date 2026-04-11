"""Factory for building ADK agents from config files."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from google.adk.agents import LlmAgent

from gclaw.config.loader import ConfigLoader

if TYPE_CHECKING:
    from gclaw.models.skill import Skill
    from gclaw.routing.router import ModelRouter
    from gclaw.skill.registry import SkillRegistry


class AgentFactory:
    """Creates ADK LlmAgent instances from soul/agent.md config files."""

    def __init__(
        self,
        loader: ConfigLoader,
        default_model: str = "gemini-2.5-flash",
        model_router: "ModelRouter | None" = None,
        skill_registry: "SkillRegistry | None" = None,
    ) -> None:
        self._loader = loader
        self._default_model = default_model
        self._router = model_router
        self._skill_registry = skill_registry

    def build(
        self,
        agent_name: str,
        soul_overlay: str | None = None,
        memories: list[str] | None = None,
        tools: list[Any] | None = None,
        sub_agents: list[LlmAgent] | None = None,
        model: Any | None = None,
        description: str | None = None,
        output_key: str | None = None,
        skills: "list[Skill] | None" = None,
        before_agent_callback: Any | None = None,
    ) -> LlmAgent:
        if skills is None and self._skill_registry is not None:
            skills = self._skill_registry.list_for_agent(agent_name)

        instruction = self._loader.build_system_prompt(
            agent_name=agent_name,
            soul_base="base",
            soul_overlay=soul_overlay,
            memories=memories,
            skills=skills,
        )

        # Model resolution: explicit > router (as ADK-ready object) > default
        adk_model: Any
        if model is not None:
            adk_model = model
        elif self._router is not None:
            adk_model = self._router.build_adk_model_for_agent(agent_name)
        else:
            adk_model = self._default_model

        safe_name = agent_name.replace("-", "_")
        kwargs: dict[str, Any] = dict(
            name=safe_name,
            model=adk_model,
            instruction=instruction,
            description=description or f"GClaw agent: {agent_name}",
            tools=tools or [],
            sub_agents=sub_agents or [],
            output_key=output_key,
        )
        if before_agent_callback is not None:
            kwargs["before_agent_callback"] = before_agent_callback
        return LlmAgent(**kwargs)
