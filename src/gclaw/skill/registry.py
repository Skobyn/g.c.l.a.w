"""Skill registry — manages skill definitions from files and Firestore."""

from __future__ import annotations

import json
import logging
import os

import yaml

from gclaw.firestore.skill_repo import SkillRepo
from gclaw.models.skill import Skill, SkillSource, SkillTrigger, TriggerMode

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
            skill_md_path = os.path.join(skill_path, "SKILL.md")

            try:
                if os.path.isfile(manifest_path):
                    # Native GClaw skill with a skill.json manifest.
                    with open(manifest_path) as f:
                        data = json.load(f)
                    skill = Skill.from_firestore_dict(data)
                elif os.path.isfile(skill_md_path):
                    # Bare SKILL.md — synthesize a minimal Skill record.
                    # Name from dir; description from the first non-heading
                    # paragraph; the SKILL.md itself becomes the
                    # instructions.
                    skill = _skill_from_markdown(entry, skill_md_path)
                else:
                    logger.debug(
                        "No skill.json or SKILL.md in %s, skipping", skill_path
                    )
                    continue

                # Set paths relative to the skill directory when not already set.
                if skill.instructions_path is None:
                    # Prefer instructions.md; else fall back to SKILL.md.
                    instructions = os.path.join(skill_path, "instructions.md")
                    if not os.path.isfile(instructions):
                        instructions = skill_md_path
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

                # Only seed on first boot — preserve any admin edits made
                # through /admin/skills. An upgrade path that refreshes
                # from disk on a version bump can layer on top later.
                if self._repo.get(skill.name) is None:
                    self._repo.save(skill)
                    loaded.append(skill)
                    logger.info("Loaded built-in skill: %s", skill.name)
                else:
                    logger.debug(
                        "Skill %s already in registry; preserving admin edits",
                        skill.name,
                    )
            except Exception:
                logger.warning(
                    "Failed to load skill from %s",
                    skill_path,
                    exc_info=True,
                )

        return loaded


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Split YAML frontmatter from the body of a SKILL.md file.

    Returns ``(frontmatter_dict, body_without_frontmatter)``. When no
    frontmatter block is present or it fails to parse cleanly, returns
    ``({}, text)`` and leaves the body untouched.
    """
    if not text.startswith("---"):
        return {}, text
    # Normalize line endings so both \n and \r\n frontmatter parse.
    normalized = text.replace("\r\n", "\n")
    lines = normalized.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, text
    end_idx = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx == -1:
        return {}, text
    try:
        data = yaml.safe_load("\n".join(lines[1:end_idx])) or {}
    except yaml.YAMLError:
        return {}, text
    if not isinstance(data, dict):
        return {}, text
    body = "\n".join(lines[end_idx + 1:])
    return data, body


def _skill_from_markdown(dir_name: str, skill_md_path: str) -> Skill:
    """Build a Skill record from a bare SKILL.md file.

    First tries to parse YAML frontmatter (the ``---`` block at the top
    of the file, as used by the handoff / debug / nano-banana-prompting
    style skills) to populate name, version, description, and
    ``allowed-tools``. Falls back to scanning the markdown body for a
    ``## Purpose`` / ``## Description`` section or the first
    non-heading paragraph when no frontmatter is present.
    """
    with open(skill_md_path, encoding="utf-8") as f:
        raw = f.read()

    frontmatter, body = _split_frontmatter(raw)

    name = str(frontmatter.get("name") or dir_name).strip() or dir_name
    version = str(frontmatter.get("version") or "1.0.0").strip() or "1.0.0"
    description = str(frontmatter.get("description") or "").strip()
    allowed_tools_raw = frontmatter.get("allowed-tools") or []
    if isinstance(allowed_tools_raw, str):
        tools_required = [
            t.strip() for t in allowed_tools_raw.split(",") if t.strip()
        ]
    elif isinstance(allowed_tools_raw, list):
        tools_required = [str(t).strip() for t in allowed_tools_raw if str(t).strip()]
    else:
        tools_required = []

    # Look for a "## Purpose" or "## Description" section first.
    if not description:
        for marker in ("## Purpose", "## Description", "## Overview"):
            for i, line in enumerate(lines):
                if line.strip().lower() == marker.lower():
                    # Grab the following non-blank lines until the next heading.
                    for j in range(i + 1, len(lines)):
                        s = lines[j].strip()
                        if s.startswith("#"):
                            break
                        if s:
                            description = s
                            break
                    if description:
                        break
            if description:
                break
    # Fall back to the first non-heading, non-blank line.
    if not description:
        for line in lines:
            s = line.strip()
            if s and not s.startswith("#"):
                description = s
                break
    if not description:
        description = f"Skill imported from {dir_name}."
    # Trim long paragraphs.
    if len(description) > 300:
        description = description[:297].rstrip() + "…"

    return Skill(
        name=name,
        description=description,
        version=version,
        trigger=SkillTrigger(mode=TriggerMode.MANUAL),
        tools_required=tools_required,
        source=SkillSource.BUILTIN,
    )
