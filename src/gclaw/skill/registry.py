"""Skill registry — manages skill definitions from files and Firestore."""

from __future__ import annotations

import json
import logging
import os

from gclaw.firestore.skill_repo import SkillRepo
from gclaw.models.skill import Skill

logger = logging.getLogger(__name__)


class SkillRegistry:
    """Central registry for skill discovery and management."""

    def __init__(self, skill_repo: SkillRepo) -> None:
        self._repo = skill_repo

    def register(self, skill: Skill) -> Skill:
        """Register a skill in the Firestore registry."""
        return self._repo.save(skill)

    def get(self, skill_name: str) -> Skill | None:
        """Get a skill by name."""
        return self._repo.get(skill_name)

    def list_all(self) -> list[Skill]:
        """List all registered skills."""
        return self._repo.list_all()

    def list_for_agent(self, agent_name: str) -> list[Skill]:
        """List skills granted to a specific agent.

        Each matching skill is recorded as a usage event — being loaded
        into an agent's prompt counts as that skill being "used" for
        the turn. Recording is best-effort and never raises.
        """
        all_skills = self._repo.list_all()
        granted = [s for s in all_skills if s.is_granted_to(agent_name)]
        try:
            from gclaw.usage.recorder import get_recorder

            recorder = get_recorder()
            if recorder.enabled:
                for skill in granted:
                    recorder.record_skill_use(
                        skill_name=skill.name,
                        agent_name=agent_name,
                    )
        except Exception:
            logger.debug("usage: skill list_for_agent recording failed",
                         exc_info=True)
        return granted

    def unregister(self, skill_name: str) -> None:
        """Remove a skill from the registry."""
        self._repo.delete(skill_name)

    def load_builtins(self, skills_dir: str) -> list[Skill]:
        """Load built-in skills from the skills/ directory.

        Each skill subdirectory should contain a skill.json file.
        Skills are registered in Firestore if not already present.

        Args:
            skills_dir: Path to the skills/ directory.

        Returns:
            List of loaded Skill objects.
        """
        loaded = []
        if not os.path.isdir(skills_dir):
            logger.warning("Skills directory not found: %s", skills_dir)
            return loaded

        for entry in os.listdir(skills_dir):
            skill_path = os.path.join(skills_dir, entry)
            if not os.path.isdir(skill_path):
                continue

            manifest_path = os.path.join(skill_path, "skill.json")
            if not os.path.isfile(manifest_path):
                logger.debug("No skill.json in %s, skipping", skill_path)
                continue

            try:
                with open(manifest_path) as f:
                    data = json.load(f)
                skill = Skill.from_firestore_dict(data)
                # Set paths relative to the skill directory
                if skill.instructions_path is None:
                    instructions = os.path.join(skill_path, "instructions.md")
                    if os.path.isfile(instructions):
                        skill = skill.model_copy(
                            update={"instructions_path": instructions}
                        )
                if skill.examples_path is None:
                    examples = os.path.join(skill_path, "examples.md")
                    if os.path.isfile(examples):
                        skill = skill.model_copy(
                            update={"examples_path": examples}
                        )

                self._repo.save(skill)
                loaded.append(skill)
                logger.info("Loaded built-in skill: %s", skill.name)
            except Exception:
                logger.warning(
                    "Failed to load skill from %s",
                    manifest_path,
                    exc_info=True,
                )

        return loaded
