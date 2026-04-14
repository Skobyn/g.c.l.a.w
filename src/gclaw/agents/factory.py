"""Factory for building ADK agents from config files."""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from google.adk.agents import LlmAgent

from gclaw.config.loader import ConfigLoader

if TYPE_CHECKING:
    from gclaw.catalog.service import CatalogService
    from gclaw.config.agent_config_service import AgentConfigService
    from gclaw.models.agent_config import AgentOverride
    from gclaw.models.catalog import ModelParams
    from gclaw.models.skill import Skill
    from gclaw.routing.router import ModelRouter
    from gclaw.skill.registry import SkillRegistry

logger = logging.getLogger(__name__)


class AgentFactory:
    """Creates ADK LlmAgent instances from soul/agent.md config files."""

    def __init__(
        self,
        loader: ConfigLoader,
        default_model: str = "gemini-2.5-flash",
        model_router: "ModelRouter | None" = None,
        skill_registry: "SkillRegistry | None" = None,
        catalog_service: "CatalogService | None" = None,
        agent_config_service: "AgentConfigService | None" = None,
    ) -> None:
        self._loader = loader
        self._default_model = default_model
        self._router = model_router
        self._skill_registry = skill_registry
        self._catalog = catalog_service
        self._agent_config_service = agent_config_service

    def _get_override(
        self, agent_name: str
    ) -> "AgentOverride | None":
        if self._agent_config_service is None:
            return None
        try:
            return self._agent_config_service.get_override(agent_name)
        except Exception:
            logger.warning(
                "factory: failed to load override for %s",
                agent_name,
                exc_info=True,
            )
            return None

    @staticmethod
    def _tool_name(tool: Any) -> str:
        """Best-effort extraction of a tool's identifier."""
        for attr in ("name", "__name__"):
            val = getattr(tool, attr, None)
            if isinstance(val, str) and val:
                return val
        return type(tool).__name__

    def _apply_override(
        self,
        agent_name: str,
        tools: list[Any] | None,
        sub_agents: list[LlmAgent] | None,
        skills: "list[Skill] | None",
    ) -> tuple[list[Any] | None, list[LlmAgent] | None, "list[Skill] | None"]:
        """Filter tools/sub_agents/skills based on the agent's override.

        - tools: drop anything whose name is in ``tools.deny``; if
          ``tools.allow`` is non-empty, keep only names in allow. Profile
          is logged only (follow-up maps presets to tool lists).
        - sub_agents: if ``subagents.allow`` is a list without "*", drop
          sub-agents whose names aren't in allow.
        - skills: if override.skills is a list, filter to that allowlist.
        """
        override = self._get_override(agent_name)
        if override is None:
            return tools, sub_agents, skills

        # Tools filter.
        if tools and (override.tools.deny or override.tools.allow):
            deny = set(override.tools.deny or [])
            allow = set(override.tools.allow or [])
            filtered: list[Any] = []
            for t in tools:
                name = self._tool_name(t)
                if name in deny:
                    continue
                if allow and name not in allow:
                    continue
                filtered.append(t)
            tools = filtered
        if override.tools.profile:
            logger.info(
                "factory: agent %s has tools.profile=%r (not yet enforced)",
                agent_name, override.tools.profile,
            )

        # Sub-agent filter.
        if sub_agents and override.subagents.allow is not None:
            allow_list = override.subagents.allow
            if "*" not in allow_list:
                allow_set = set(allow_list)
                sub_agents = [
                    a for a in sub_agents
                    if getattr(a, "name", None) in allow_set
                    or getattr(a, "name", "").replace("_", "-") in allow_set
                ]

        # Skills filter.
        if skills and override.skills is not None:
            allow_skills = set(override.skills)
            skills = [s for s in skills if s.name in allow_skills]

        # Thinking level: stored for future use; log a TODO for Gemini.
        if override.model.thinking is not None:
            logger.debug(
                "factory: agent %s thinking=%s (TODO: wire into LiteLlm "
                "metadata / Gemini generation_config)",
                agent_name, override.model.thinking,
            )

        return tools, sub_agents, skills

    def _apply_params_override(
        self, adk_model: Any, params: "ModelParams | None"
    ) -> Any:
        """Apply per-call ``ModelParams`` overrides to a LiteLlm instance.

        For bare-string (Gemini/Vertex) models, per-call params are not
        wired through this factory path — ADK agent-level generation
        config handles that today. Logs and returns the object unchanged.
        """
        if params is None:
            return adk_model
        try:
            from google.adk.models.lite_llm import LiteLlm
        except Exception:
            return adk_model
        if not isinstance(adk_model, LiteLlm):
            return adk_model

        dumped = params.model_dump(exclude_none=True)
        extra = dumped.pop("extra", None) or {}
        # Merge extra first, then top-level so top-level wins.
        for key, value in extra.items():
            setattr(adk_model, key, value)
        for key, value in dumped.items():
            setattr(adk_model, key, value)
        return adk_model

    def _resolve_agent_model(self, agent_name: str) -> Any | None:
        """Resolve a frontmatter ``model:`` to an ADK-ready object.

        Returns None when the agent has no ``model:`` frontmatter, or
        when resolution fails (warning already logged). Requires a
        ``catalog_service`` — without it, frontmatter refs are ignored
        and a warning is logged once.
        """
        try:
            ref = self._loader.load_agent_model_ref(agent_name)
        except Exception:
            logger.warning(
                "agent %s: failed to parse model frontmatter",
                agent_name,
                exc_info=True,
            )
            return None
        if ref is None:
            return None
        if self._catalog is None:
            logger.warning(
                "agent %s: model frontmatter %r present but no catalog "
                "service wired — falling back",
                agent_name,
                ref.name,
            )
            return None

        from gclaw.catalog.adk_builder import build_adk_override_from_model
        from gclaw.catalog.model_resolver import resolve_agent_model

        resolved = resolve_agent_model(ref, self._catalog)
        if resolved is None:
            return None
        provider, model = resolved
        api_key = self._catalog.resolve_api_key(provider)
        adk_model = build_adk_override_from_model(provider, model, api_key)
        return self._apply_params_override(adk_model, ref.params)

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

        tools, sub_agents, skills = self._apply_override(
            agent_name, tools, sub_agents, skills
        )

        instruction = self._loader.build_system_prompt(
            agent_name=agent_name,
            soul_base="base",
            soul_overlay=soul_overlay,
            memories=memories,
            skills=skills,
        )

        # Model resolution priority:
        # explicit param > frontmatter > router > default
        adk_model: Any
        if model is not None:
            adk_model = model
        else:
            fm_model = self._resolve_agent_model(agent_name)
            if fm_model is not None:
                adk_model = fm_model
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
