"""Load and merge soul/agent.md configuration files into system prompts."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gclaw.models.skill import Skill
    from gclaw.skill.loader import SkillLoader


class ConfigLoader:
    """Loads soul and agent definition files from the config directory.

    Directory structure expected:
        config_dir/
            soul/
                base.md
                workspace.md
                dev.md
                ...
            agents/
                orchestrator.md
                workspace-mgr.md
                ...
    """

    def __init__(
        self,
        config_dir: str,
        skill_loader: SkillLoader | None = None,
    ) -> None:
        self._config_dir = config_dir
        self._skill_loader = skill_loader

    def load_soul(self, base: str, overlay: str | None = None) -> str:
        base_path = os.path.join(self._config_dir, "soul", f"{base}.md")
        if not os.path.isfile(base_path):
            raise FileNotFoundError(f"Soul base not found: {base_path}")

        with open(base_path) as f:
            content = f.read()

        if overlay:
            overlay_path = os.path.join(
                self._config_dir, "soul", f"{overlay}.md"
            )
            if os.path.isfile(overlay_path):
                with open(overlay_path) as f:
                    content += "\n" + f.read()

        return content

    def load_agent(self, agent_name: str) -> str:
        path = os.path.join(self._config_dir, "agents", f"{agent_name}.md")
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Agent definition not found: {path}")

        with open(path) as f:
            return f.read()

    def build_system_prompt(
        self,
        agent_name: str,
        soul_base: str = "base",
        soul_overlay: str | None = None,
        memories: list[str] | None = None,
        skills: list[Skill] | None = None,
    ) -> str:
        parts: list[str] = []

        # Agent definition
        agent_def = self.load_agent(agent_name)
        parts.append(f"# Agent Role\n\n{agent_def}")

        # Soul
        soul = self.load_soul(soul_base, overlay=soul_overlay)
        parts.append(f"# Personality & User Context\n\n{soul}")

        # Injected memories
        if memories:
            formatted = "\n".join(f"- {m}" for m in memories)
            parts.append(
                f"# Relevant Memories\n\n{formatted}"
            )

        # Skill instructions
        if skills and self._skill_loader is not None:
            skills_prompt = self._skill_loader.build_skills_prompt(skills)
            if skills_prompt:
                parts.append(skills_prompt)

        return "\n\n---\n\n".join(parts)
