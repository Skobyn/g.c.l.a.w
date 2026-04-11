"""In-process skill repository for built-in skills.

SkillRegistry was designed around a Firestore-backed SkillRepo so per-user
dynamic skills can be persisted. For built-in skills loaded from disk at
startup there is no reason to pay the Firestore round-trip — this repo
implements the same interface against a plain dict.
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
