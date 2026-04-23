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
        tool_binding_service: Any | None = None,
    ) -> None:
        self._loader = loader
        self._default_model = default_model
        self._router = model_router
        self._skill_registry = skill_registry
        self._catalog = catalog_service
        self._agent_config_service = agent_config_service
        # Tool catalog binding — resolves override.tools.catalog_tool_ids
        # into callables. None is valid; the factory skips catalog-tool
        # merging in that case (back-compat for the legacy allow/deny
        # path).
        self._tool_binding = tool_binding_service

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

    def _merge_catalog_tools(
        self, agent_name: str, tools: list[Any] | None
    ) -> list[Any]:
        """Append override.tools.catalog_tool_ids → callables onto tools.

        Returns a new list; input is unchanged. De-duplicates by
        tool-name so the same function pulled in through both the
        legacy allow-list and the catalog doesn't appear twice.
        """
        merged: list[Any] = list(tools or [])
        if self._tool_binding is None:
            return merged
        override = self._get_override(agent_name)
        if override is None:
            return merged
        ids = getattr(getattr(override, "tools", None), "catalog_tool_ids", []) or []
        if not ids:
            return merged
        resolved = self._tool_binding.resolve_catalog_tools(ids)
        if not resolved:
            return merged
        seen_names: set[str] = set()
        seen_ids: set[int] = set()
        for t in merged:
            seen_ids.add(id(t))
            n = self._tool_name(t)
            # Skip generic class-name fallbacks (e.g. "McpToolset") —
            # they're not stable identifiers for dedupe purposes.
            if n and not n.startswith("McpToolset"):
                seen_names.add(n)
        for t in resolved:
            if id(t) in seen_ids:
                continue
            n = self._tool_name(t)
            if n and n in seen_names and not n.startswith("McpToolset"):
                continue
            merged.append(t)
            seen_ids.add(id(t))
            if n:
                seen_names.add(n)
        return merged

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

    def _resolve_ref_to_adk(
        self, ref_name: str, params: Any | None = None
    ) -> Any | None:
        """Resolve a catalog ref string (``Provider/model_id`` or bare id)
        to an ADK-ready model object via the catalog service.

        Returns None when the catalog is unset or resolution fails
        (warning logged). ``params`` is an optional ``ModelParams`` applied
        to LiteLlm instances.
        """
        if not ref_name or self._catalog is None:
            return None
        from gclaw.catalog.adk_builder import build_adk_override_from_model
        from gclaw.catalog.model_resolver import resolve_agent_model
        from gclaw.models.catalog import AgentModelRef

        try:
            ref = AgentModelRef(name=ref_name, params=params)
        except Exception:
            logger.warning(
                "factory: invalid model ref %r", ref_name, exc_info=True,
            )
            return None
        try:
            resolved = resolve_agent_model(ref, self._catalog)
        except Exception:
            logger.warning(
                "factory: resolve_agent_model failed for %r",
                ref_name,
                exc_info=True,
            )
            return None
        if resolved is None:
            return None
        provider, model = resolved
        try:
            api_key = self._catalog.resolve_api_key(provider)
        except Exception:
            logger.warning(
                "factory: resolve_api_key failed for provider %s",
                getattr(provider, "name", provider),
                exc_info=True,
            )
            api_key = None
        catalog = self._catalog
        captured_provider = provider

        def _key_provider():
            return catalog.resolve_api_key(captured_provider)

        try:
            adk_model = build_adk_override_from_model(
                provider, model, api_key, key_provider=_key_provider
            )
        except Exception:
            logger.warning(
                "factory: build_adk_override_from_model failed for %r",
                ref_name,
                exc_info=True,
            )
            return None
        return self._apply_params_override(adk_model, params)

    def resolve_model_chain(self, agent_name: str) -> list[Any]:
        """Return ``[primary, *fallbacks]`` as ADK-ready model objects.

        Resolution rules:
        - If an override exists with ``model.primary`` set: start with
          that, then append each ``model.fallbacks`` entry. Entries that
          fail to resolve are skipped (warning logged) rather than
          raising.
        - Otherwise: fall back to the router-resolved primary (no
          fallbacks). If no router either, return ``[]``.
        """
        chain: list[Any] = []
        override = self._get_override(agent_name)

        if override is not None and override.model.primary:
            primary = self._resolve_ref_to_adk(override.model.primary)
            if primary is not None:
                chain.append(primary)
            else:
                logger.warning(
                    "factory: agent %s primary %r did not resolve — skipping",
                    agent_name,
                    override.model.primary,
                )
            for fb_ref in override.model.fallbacks or []:
                fb = self._resolve_ref_to_adk(fb_ref)
                if fb is None:
                    logger.warning(
                        "factory: agent %s fallback %r did not resolve "
                        "— skipping",
                        agent_name,
                        fb_ref,
                    )
                    continue
                chain.append(fb)
            return chain

        # No override primary: router-resolved primary only.
        if self._router is not None:
            try:
                chain.append(self._router.build_adk_model_for_agent(agent_name))
            except Exception:
                logger.warning(
                    "factory: router.build_adk_model_for_agent(%s) failed",
                    agent_name,
                    exc_info=True,
                )
        return chain

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
        # Capture a closure that re-resolves the key on demand so
        # OAuth-backed providers (Anthropic OAuth, Copilot exchange)
        # get a fresh token per call instead of baking the boot-time
        # value into the LiteLlm instance.
        catalog = self._catalog
        captured_provider = provider

        def _key_provider():
            return catalog.resolve_api_key(captured_provider)

        adk_model = build_adk_override_from_model(
            provider, model, api_key, key_provider=_key_provider
        )
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

        # Merge catalog-selected tools onto the caller-supplied list
        # BEFORE allow/deny filtering runs, so legacy filters apply
        # uniformly across hard-coded and catalog-origin tools.
        tools = self._merge_catalog_tools(agent_name, tools)

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
        adk_model = self._resolve_model(agent_name, explicit=model)

        return self._assemble_agent(
            agent_name=agent_name,
            instruction=instruction,
            adk_model=adk_model,
            tools=tools,
            sub_agents=sub_agents,
            description=description,
            output_key=output_key,
            before_agent_callback=before_agent_callback,
        )

    # ── shared assembly helpers ────────────────────────────────────────

    def _resolve_model(
        self, agent_name: str, *, explicit: Any | None = None
    ) -> Any:
        """Resolve the ADK model object for an agent.

        Order: explicit > frontmatter > router > default. Used by both
        the persistent ``build`` path and the ephemeral ``build_transient``
        path so the resolution rules stay in one place.
        """
        if explicit is not None:
            return explicit
        fm_model = self._resolve_agent_model(agent_name)
        if fm_model is not None:
            return fm_model
        if self._router is not None:
            return self._router.build_adk_model_for_agent(agent_name)
        return self._default_model

    def _assemble_agent(
        self,
        *,
        agent_name: str,
        instruction: str,
        adk_model: Any,
        tools: list[Any] | None,
        sub_agents: list[LlmAgent] | None,
        description: str | None,
        output_key: str | None,
        before_agent_callback: Any | None,
    ) -> LlmAgent:
        """Stamp the final ``LlmAgent`` from a fully-resolved input set.

        Both ``build`` and ``build_transient`` route through here so the
        constructor-arg shape stays identical between persistent and
        ephemeral agents.
        """
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

    # ── transient (eval-only) path ─────────────────────────────────────

    def build_transient(
        self,
        *,
        agent_name: str,
        body: str,
        soul_overlay: str | None = None,
        tools: list[Any] | None = None,
        model: Any | None = None,
        description: str | None = None,
    ) -> LlmAgent:
        """Build a one-off LlmAgent that doesn't touch Firestore.

        Used by the agent-architect to score a draft via eval before
        registering. The returned LlmAgent is identical in shape to one
        built via the regular path (soul layering, instruction assembly)
        — but no override is created and no file is written. Caller is
        responsible for tearing down references.

        The transient build path deliberately skips:
        - Firestore override lookups (``_apply_override``,
          ``_merge_catalog_tools``) — drafts have no override yet.
        - Memory recall callbacks — pass ``before_agent_callback=None``
          implicitly by not wiring one. Vertex Memory Bank calls would
          dominate the eval pass wall-clock otherwise.
        - The agent baseline ``.md`` file lookup — ``body`` is the
          authoritative source of truth for the prompt.

        Args:
            agent_name: Identifier used for the LlmAgent's name and any
                soul-overlay file lookup. Does NOT need to exist on disk
                or in Firestore.
            body: Full agent body markdown (the "Agent Role" content
                normally read from ``agents/<name>.md``).
            soul_overlay: Optional name of a soul overlay file under
                ``soul/`` to layer onto ``soul/base.md``. Inline
                overlay markdown is NOT supported here — overlay must
                reference an existing file or be None (eval drafts
                default to the base soul).
            tools: Callables to bind. None = no tools.
            model: Explicit ADK model object; falls through to router /
                default when None. The architect typically passes the
                resolved orchestrator model so eval doesn't depend on
                catalog state.
            description: Short description on the LlmAgent.

        Returns:
            A live ``LlmAgent`` ready to be wrapped in an ``AgentRunner``
            for eval. Not registered, not persisted, not discoverable
            via ``factory.build(agent_name)``.
        """
        instruction = self._build_transient_prompt(
            agent_name=agent_name,
            body=body,
            soul_overlay=soul_overlay,
        )

        adk_model = self._resolve_model(agent_name, explicit=model)
        logger.info(
            "factory.build_transient: %s (model=%s, tools=%d) — no "
            "override / no persistence",
            agent_name,
            getattr(adk_model, "model", adk_model),
            len(tools or []),
        )
        return self._assemble_agent(
            agent_name=agent_name,
            instruction=instruction,
            adk_model=adk_model,
            tools=tools,
            sub_agents=None,
            description=description,
            output_key=None,
            before_agent_callback=None,
        )

    def _build_transient_prompt(
        self,
        *,
        agent_name: str,
        body: str,
        soul_overlay: str | None,
    ) -> str:
        """Stitch a system prompt for a transient agent without touching
        the agent file system.

        Mirrors the structure of ``ConfigLoader.build_system_prompt`` —
        Agent Role + Current time + Personality — but uses ``body``
        directly instead of resolving from disk / Firestore. The user
        profile and memory blocks are intentionally omitted: an eval
        run shouldn't depend on personal context.
        """
        loader = self._loader
        parts: list[str] = [f"# Agent Role\n\n{body}"]
        parts.append(f"# Current time\n\n{loader.current_time_block()}")
        try:
            soul = loader.load_soul("base", overlay=soul_overlay)
        except FileNotFoundError:
            soul = ""
        if soul:
            parts.append(f"# Personality\n\n{soul}")
        return "\n\n---\n\n".join(parts)
