"""Skill discovery — find skills by context for dynamic invocation.

Skills can be discovered by:
1. Context matching — user's current context matches skill trigger contexts
2. Description matching — fallback keyword matching against skill descriptions
3. Command matching — direct /command invocation
"""

from __future__ import annotations

import logging

from gclaw.models.skill import Skill, TriggerMode
from gclaw.skill.registry import SkillRegistry

logger = logging.getLogger(__name__)


class SkillDiscovery:
    """Discovers relevant skills based on context."""

    def __init__(self, registry: SkillRegistry) -> None:
        self._registry = registry

    def discover(
        self,
        agent_name: str,
        context: str,
    ) -> list[Skill]:
        """Find skills matching the current context.

        Only auto or both trigger modes are considered — manual-only
        skills must be invoked via command.

        Args:
            agent_name: The agent looking for skills.
            context: Description of what the agent is currently doing.

        Returns:
            List of matching skills, ordered by relevance.
        """
        available = self._registry.list_for_agent(agent_name)
        matches = []

        for skill in available:
            # Skip manual-only skills
            if skill.trigger.mode == TriggerMode.MANUAL:
                continue

            # Try context match first
            if skill.matches_context(context):
                matches.append(skill)
                continue

            # Fall back to description keyword matching
            if self._description_matches(skill.description, context):
                matches.append(skill)

        return matches

    def find_by_command(
        self,
        agent_name: str,
        command: str,
    ) -> Skill | None:
        """Find a skill by its slash command.

        Args:
            agent_name: The agent invoking the command.
            command: The slash command (e.g., "/draft-email").

        Returns:
            The matching Skill, or None.
        """
        available = self._registry.list_for_agent(agent_name)
        for skill in available:
            if skill.trigger.command == command:
                return skill
        return None

    def _description_matches(self, description: str, context: str) -> bool:
        """Simple keyword matching between description and context."""
        desc_words = set(description.lower().split())
        context_words = set(context.lower().split())
        # Match if at least 2 significant words overlap
        overlap = desc_words & context_words
        # Filter out common stop words
        stop_words = {"a", "an", "the", "is", "are", "to", "for", "and", "or", "of", "in", "on", "with"}
        significant = overlap - stop_words
        return len(significant) >= 2
