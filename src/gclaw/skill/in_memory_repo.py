"""In-process skill repository for tests.

Production code uses ``gclaw.firestore.skill_repo.SkillRepo`` so skill
state is shared across workers and survives restarts. This in-memory
variant implements the same interface against a plain dict and is kept
around so tests can exercise the registry without a Firestore emulator.
"""

from __future__ import annotations

from gclaw.models.skill import Skill


class InMemorySkillRepo:
    """Drop-in replacement for SkillRepo backed by a dict."""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def save(self, skill: Skill) -> Skill:
        self._skills[skill.name] = skill
        return skill

    def get(self, skill_name: str) -> Skill | None:
        return self._skills.get(skill_name)

    def delete(self, skill_name: str) -> None:
        self._skills.pop(skill_name, None)

    def list_all(self) -> list[Skill]:
        return list(self._skills.values())
