"""AgentConfigService — merges AgentOverride docs atop file-backed baselines."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from gclaw.config.loader import ConfigLoader
from gclaw.models.agent_config import (
    AgentIdentity,
    AgentModelSpec,
    AgentOverride,
    AgentSubagentsSpec,
    AgentToolsSpec,
)

if TYPE_CHECKING:
    from gclaw.firestore.agent_override_repo import AgentOverrideRepo
    from gclaw.skill.registry import SkillRegistry

logger = logging.getLogger(__name__)


class AgentConfigService:
    """Merges Firestore AgentOverride on top of file-backed agent baseline."""

    def __init__(
        self,
        override_repo: "AgentOverrideRepo",
        loader: ConfigLoader,
        skill_registry: "SkillRegistry | None",
        agents_dir: Path | str,
    ) -> None:
        self._repo = override_repo
        self._loader = loader
        self._skill_registry = skill_registry
        self._agents_dir = Path(agents_dir)

    # -- discovery helpers ---------------------------------------------------

    def _baseline_agent_names(self) -> list[str]:
        if not self._agents_dir.is_dir():
            return []
        return sorted(
            p.stem for p in self._agents_dir.iterdir()
            if p.is_file() and p.suffix == ".md"
        )

    def _has_baseline(self, agent_name: str) -> bool:
        return (self._agents_dir / f"{agent_name}.md").is_file()

    # -- override provider ---------------------------------------------------

    def get_override(self, agent_name: str) -> AgentOverride | None:
        """Return the current override for an agent, or None. Suitable
        for passing to ``ConfigLoader`` as ``override_provider``.
        """
        try:
            return self._repo.get(agent_name)
        except Exception:
            logger.warning(
                "agent_config: failed to load override for %s",
                agent_name,
                exc_info=True,
            )
            return None

    # -- reads ---------------------------------------------------------------

    def list_agents(self) -> list[dict]:
        """Union of file-backed + standalone overrides.

        Each entry:
          {name, display_name, description, has_override, enabled,
           is_standalone, model_ref, heartbeat_enabled, tools_profile}
        """
        try:
            overrides_by_name = {o.agent_name: o for o in self._repo.list_all()}
        except Exception:
            logger.warning("agent_config: list_all failed", exc_info=True)
            overrides_by_name = {}

        baseline_names = set(self._baseline_agent_names())
        all_names = sorted(baseline_names | set(overrides_by_name.keys()))

        out: list[dict] = []
        for name in all_names:
            override = overrides_by_name.get(name)
            has_baseline = name in baseline_names
            display_name: str | None = None
            description: str | None = None
            model_ref: str | None = None
            heartbeat_enabled = False
            tools_profile: str | None = None

            # Pull baseline-derived hints when available.
            if has_baseline:
                try:
                    hb = self._loader.load_agent_heartbeat_config(name)
                    if hb is not None:
                        heartbeat_enabled = bool(hb.enabled)
                except Exception:
                    pass
                try:
                    ref = self._loader.load_agent_model_ref(name)
                    if ref is not None:
                        model_ref = ref.name
                except Exception:
                    pass

            if override is not None:
                if override.identity.display_name:
                    display_name = override.identity.display_name
                if override.identity.description:
                    description = override.identity.description
                if override.model.primary:
                    model_ref = override.model.primary
                if override.heartbeat is not None:
                    heartbeat_enabled = bool(override.heartbeat.enabled)
                if override.tools.profile:
                    tools_profile = override.tools.profile

            out.append({
                "name": name,
                "display_name": display_name or name,
                "description": description,
                "has_override": override is not None,
                "enabled": override.enabled if override is not None else True,
                "is_standalone": (
                    override.is_standalone if override is not None else False
                ),
                "has_baseline": has_baseline,
                "model_ref": model_ref,
                "heartbeat_enabled": heartbeat_enabled,
                "tools_profile": tools_profile,
            })
        return out

    def get_effective_config(self, agent_name: str) -> dict:
        """Return merged config for ``agent_name``.

        Fields:
          name, identity, model, tools, subagents, skills, heartbeat,
          system_prompt, body, soul_overlay, is_standalone, has_baseline,
          has_override, enabled.
        """
        has_baseline = self._has_baseline(agent_name)
        override = self.get_override(agent_name)

        if not has_baseline and override is None:
            raise FileNotFoundError(
                f"agent {agent_name!r} has neither a baseline .md nor an override"
            )

        # Baseline pulls
        baseline_body: str | None = None
        baseline_heartbeat = None
        baseline_model_ref: str | None = None
        if has_baseline:
            try:
                baseline_body = self._loader.load_agent(agent_name)
            except Exception:
                baseline_body = None
            try:
                baseline_heartbeat = self._loader.load_agent_heartbeat_config(
                    agent_name
                )
            except Exception:
                baseline_heartbeat = None
            try:
                ref = self._loader.load_agent_model_ref(agent_name)
                if ref is not None:
                    baseline_model_ref = ref.name
            except Exception:
                baseline_model_ref = None

        identity = (
            override.identity if override is not None else AgentIdentity()
        )
        model = (
            override.model if override is not None else AgentModelSpec()
        )
        tools = (
            override.tools if override is not None else AgentToolsSpec()
        )
        subagents = (
            override.subagents if override is not None else AgentSubagentsSpec()
        )

        # Effective primary model — override wins, else baseline frontmatter.
        effective_model_primary = model.primary or baseline_model_ref

        # Skills: None = inherit registry default; [] = deny all; list = allowlist.
        if override is not None and override.skills is not None:
            effective_skills: list[str] | None = list(override.skills)
        else:
            effective_skills = None  # inherit

        # Heartbeat: override wins entirely.
        effective_heartbeat = (
            override.heartbeat if override is not None else baseline_heartbeat
        )

        # Body: body_override > baseline.
        body = baseline_body
        if override is not None and override.body_override is not None:
            body = override.body_override

        # System prompt: system_prompt_override replaces the whole body.
        system_prompt = body
        if override is not None and override.system_prompt_override is not None:
            system_prompt = override.system_prompt_override

        soul_overlay = override.soul_overlay if override is not None else None

        return {
            "name": agent_name,
            "identity": identity.model_dump(mode="json"),
            "model": {
                **model.model_dump(mode="json"),
                "effective_primary": effective_model_primary,
            },
            "tools": tools.model_dump(mode="json"),
            "subagents": subagents.model_dump(mode="json"),
            "skills": effective_skills,
            "heartbeat": (
                effective_heartbeat.model_dump(mode="json")
                if effective_heartbeat is not None
                else None
            ),
            "system_prompt": system_prompt,
            "body": body,
            "soul_overlay": soul_overlay,
            "is_standalone": (
                override.is_standalone if override is not None else False
            ),
            "has_baseline": has_baseline,
            "has_override": override is not None,
            "enabled": override.enabled if override is not None else True,
        }

    # -- writes --------------------------------------------------------------

    def create_standalone(
        self,
        *,
        agent_name: str,
        body: str,
        display_name: str | None = None,
        description: str | None = None,
        emoji: str | None = None,
        model_primary: str | None = None,
        soul_overlay: str | None = None,
        **extra: Any,
    ) -> AgentOverride:
        """Create a new standalone (UI-only) agent with no baseline .md."""
        if not agent_name:
            raise ValueError("agent_name is required")
        if not body:
            raise ValueError("body is required for standalone agents")
        if self._has_baseline(agent_name):
            raise ValueError(
                f"agent {agent_name!r} already has a baseline .md — "
                "use upsert_override instead"
            )
        if self._repo.get(agent_name) is not None:
            raise ValueError(f"override already exists for {agent_name!r}")

        override = AgentOverride(
            agent_name=agent_name,
            identity=AgentIdentity(
                display_name=display_name,
                description=description,
                emoji=emoji,
            ),
            model=AgentModelSpec(primary=model_primary) if model_primary else AgentModelSpec(),
            body_override=body,
            soul_overlay=soul_overlay,
            is_standalone=True,
        )
        return self._repo.create(override)

    def upsert_override(self, agent_name: str, patch: dict) -> AgentOverride:
        """Patch an existing override, or create a new file-backed override.

        ``patch`` is a partial dict shaped like ``AgentOverride``. Nested
        BaseModel fields may be passed as dicts; unknown keys are ignored.
        List fields (fallbacks, allow, deny) REPLACE when present.
        """
        existing = self._repo.get(agent_name)
        if existing is None:
            existing = AgentOverride(
                agent_name=agent_name,
                is_standalone=False,
            )

        # Start from a serializable dict, apply the patch, rehydrate.
        current = existing.model_dump(mode="python")
        # Force the agent_name — never let a patch change it.
        patch = dict(patch or {})
        patch.pop("agent_name", None)
        patch.pop("created_at", None)

        for key, value in patch.items():
            if value is None and key in (
                "skills", "heartbeat", "system_prompt_override",
                "body_override", "soul_overlay",
            ):
                current[key] = None
                continue
            if key in ("identity", "model", "tools", "subagents") and isinstance(
                value, dict
            ):
                # Shallow-merge nested specs so callers can patch just one field.
                merged = dict(current.get(key) or {})
                merged.update(value)
                current[key] = merged
            else:
                current[key] = value

        current["agent_name"] = agent_name
        current["updated_at"] = datetime.now(timezone.utc)
        rebuilt = AgentOverride.model_validate(current)
        return self._repo.update(rebuilt)

    def delete_override(self, agent_name: str) -> dict:
        """Delete an override. If standalone → full delete; file-backed →
        reverts to baseline. Returns ``{deleted, reverted_to_baseline}``.
        """
        existing = self._repo.get(agent_name)
        if existing is None:
            # Nothing to delete. Report baseline presence for the UI.
            return {
                "deleted": False,
                "reverted_to_baseline": self._has_baseline(agent_name),
            }
        self._repo.delete(agent_name)
        return {
            "deleted": True,
            "reverted_to_baseline": (
                self._has_baseline(agent_name) and not existing.is_standalone
            ),
        }

    # -- baseline raw reader -------------------------------------------------

    def read_baseline(self, agent_name: str) -> str | None:
        """Return raw baseline .md file content, or None if no baseline."""
        path = self._agents_dir / f"{agent_name}.md"
        if not path.is_file():
            return None
        return path.read_text()
