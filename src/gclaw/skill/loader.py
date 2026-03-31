"""Skill loader — reads skill files and builds prompt sections.

Each skill has:
- skill.json — manifest with name, description, trigger, config, grants
- instructions.md — detailed instructions for how to perform the skill
- examples.md — few-shot examples
"""

from __future__ import annotations

import logging
import os

from gclaw.models.skill import Skill

logger = logging.getLogger(__name__)


class SkillLoader:
    """Loads skill files and builds prompt-injectable sections."""

    def load_instructions(self, skill: Skill) -> str:
        """Load the instructions.md file for a skill."""
        if skill.instructions_path is None:
            return ""
        return self._read_file(skill.instructions_path)

    def load_examples(self, skill: Skill) -> str:
        """Load the examples.md file for a skill."""
        if skill.examples_path is None:
            return ""
        return self._read_file(skill.examples_path)

    def build_prompt_section(self, skill: Skill) -> str:
        """Build a prompt section for a single skill.

        Format:
            ## Skill: <name>
            <description>

            ### Configuration
            <config as key-value pairs>

            ### Instructions
            <instructions.md content>

            ### Examples
            <examples.md content>
        """
        parts = [
            f"## Skill: {skill.name}",
            skill.description,
        ]

        if skill.config:
            parts.append("")
            parts.append("### Configuration")
            for key, value in skill.config.items():
                parts.append(f"- {key}: {value}")

        instructions = self.load_instructions(skill)
        if instructions:
            parts.append("")
            parts.append("### Instructions")
            parts.append(instructions)

        examples = self.load_examples(skill)
        if examples:
            parts.append("")
            parts.append("### Examples")
            parts.append(examples)

        return "\n".join(parts)

    def build_skills_prompt(self, skills: list[Skill]) -> str:
        """Build a combined prompt section for multiple skills.

        Args:
            skills: List of skills to include in the prompt.

        Returns:
            Formatted skills section for injection into system prompt.
        """
        if not skills:
            return ""

        sections = ["# Available Skills", ""]
        for skill in skills:
            sections.append(self.build_prompt_section(skill))
            sections.append("")

        return "\n".join(sections).strip()

    def _read_file(self, path: str) -> str:
        """Read a file, returning empty string if not found."""
        if not os.path.isfile(path):
            logger.debug("Skill file not found: %s", path)
            return ""
        with open(path) as f:
            return f.read()
