"""Load and merge soul/agent.md configuration files into system prompts."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Callable

import yaml

from gclaw.heartbeat.config import HeartbeatConfig
from gclaw.models.catalog import AgentModelRef, ModelParams

if TYPE_CHECKING:
    from gclaw.models.agent_config import AgentOverride
    from gclaw.models.skill import Skill
    from gclaw.skill.loader import SkillLoader


_FRONTMATTER_DELIM = "---"

# Agents that receive the shared user.md profile by default when neither
# an override nor a frontmatter key pins the value. The orchestrator is
# the conversational front door, so it always sees the user. The profile
# manager maintains user.md and therefore also needs it. Everyone else
# stays opt-in so managers and specialist tool-routers don't waste
# context on personal history they won't use.
_USER_KNOWLEDGE_DEFAULT_ON: frozenset[str] = frozenset({
    "orchestrator",
    "profile-mgr",
})


def _split_frontmatter(text: str) -> tuple[dict[str, Any] | None, str]:
    """Split optional YAML frontmatter from a markdown document.

    Returns (frontmatter_dict_or_None, body). Frontmatter must be the very
    first thing in the file, delimited by lines containing only '---'.
    """
    # Must start with delimiter on line 1 (allow a leading BOM / whitespace
    # on that line? keep it strict — line must be exactly '---').
    if not text.startswith(_FRONTMATTER_DELIM):
        return None, text

    # Split into lines, preserving line endings semantics for the body.
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != _FRONTMATTER_DELIM:
        return None, text

    # Find closing delimiter.
    closing_idx: int | None = None
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == _FRONTMATTER_DELIM:
            closing_idx = i
            break

    if closing_idx is None:
        # No closing fence — treat whole file as body.
        return None, text

    fm_text = "".join(lines[1:closing_idx])
    body = "".join(lines[closing_idx + 1 :])
    # Strip a single leading newline from the body if present for cleanliness.
    if body.startswith("\n"):
        body = body[1:]

    try:
        data = yaml.safe_load(fm_text) if fm_text.strip() else None
    except yaml.YAMLError as e:
        raise ValueError(f"invalid YAML frontmatter: {e}") from e

    if data is None:
        return None, body
    if not isinstance(data, dict):
        raise ValueError(
            f"frontmatter must be a mapping, got {type(data).__name__}"
        )
    return data, body


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

    Agent .md files MAY begin with YAML frontmatter delimited by '---' for
    per-agent configuration (e.g. heartbeat settings). The frontmatter is
    stripped before the body is used as a system prompt.
    """

    def __init__(
        self,
        config_dir: str,
        skill_loader: SkillLoader | None = None,
        override_provider: (
            Callable[[str], "AgentOverride | None"] | None
        ) = None,
        user_timezone: str = "UTC",
    ) -> None:
        self._config_dir = config_dir
        self._skill_loader = skill_loader
        self._override_provider = override_provider
        self._user_timezone = user_timezone

    def set_user_timezone(self, tz: str) -> None:
        """Hot-swap the timezone used in the Current time block.

        Called by admin routes when the user updates their timezone
        from the UI so the change takes effect on the very next
        prompt build, no redeploy.
        """
        self._user_timezone = tz or "UTC"

    def get_user_timezone(self) -> str:
        return self._user_timezone or "UTC"

    def _get_override(self, agent_name: str) -> "AgentOverride | None":
        if self._override_provider is None:
            return None
        try:
            return self._override_provider(agent_name)
        except Exception:
            # Override lookup must never break baseline loading.
            return None

    def set_override_provider(
        self,
        provider: Callable[[str], "AgentOverride | None"] | None,
    ) -> None:
        """Set (or clear) the override provider. Used when the service is
        constructed after the loader (chicken-and-egg at app boot)."""
        self._override_provider = provider

    def current_time_block(self) -> str:
        """Render a '# Current time' section with UTC + user-local clock.

        Gemini has no inherent notion of wall-clock time or the user's
        timezone — without this, agents guess (usually wrong, usually
        UTC) when they reason about "at 8am tomorrow" or "in two
        hours". We compute it fresh on every prompt build so it stays
        accurate for the turn the agent is about to take.
        """
        from datetime import datetime, timezone as _dt_tz

        now_utc = datetime.now(_dt_tz.utc)
        tz_name = self._user_timezone or "UTC"
        local_str = now_utc.astimezone(_dt_tz.utc).isoformat(timespec="seconds")
        try:
            from zoneinfo import ZoneInfo

            local_dt = now_utc.astimezone(ZoneInfo(tz_name))
            local_str = local_dt.strftime("%Y-%m-%d %H:%M %Z")
        except Exception:
            # Unknown IANA name — fall back to UTC with a warning note.
            tz_name = f"{tz_name} (invalid — falling back to UTC)"
            local_str = now_utc.strftime("%Y-%m-%d %H:%M UTC")

        return (
            f"UTC: {now_utc.isoformat(timespec='seconds')}\n"
            f"User local ({tz_name}): {local_str}\n"
            "Use the user-local time when interpreting phrases like 'today', "
            "'tomorrow', 'this morning', or when setting reminders/crons. "
            "Persist timestamps in UTC; display them in the user's local zone."
        )

    def load_user_profile(self) -> str:
        """Return the shared user-profile markdown, or "" if missing.

        The profile lives at ``<config_dir>/user.md`` and captures stable
        facts every agent should know about the user (name, role, timezone,
        communication preferences). Evolving preferences keep living in
        Memory Bank — this file intentionally holds the slow-changing
        baseline so agents don't need to derive it from memory every call.
        """
        path = os.path.join(self._config_dir, "user.md")
        if not os.path.isfile(path):
            return ""
        with open(path) as f:
            return f.read().strip()

    def user_profile_path(self) -> str:
        """Return the absolute path of the shared user profile file."""
        return os.path.join(self._config_dir, "user.md")

    def user_profile_is_blank(self) -> bool:
        """True when user.md is missing, empty, or whitespace-only."""
        return not self.load_user_profile()

    def resolve_user_knowledge(self, agent_name: str) -> bool:
        """Resolve whether ``agent_name`` receives the shared user.md.

        Resolution order (first match wins):
          1. Firestore-backed AgentOverride ``user_knowledge`` flag.
          2. Agent-file frontmatter key ``user_knowledge``.
          3. Per-agent default: on for orchestrator + profile-mgr,
             off for everyone else.
        """
        override = self._get_override(agent_name)
        if override is not None and override.user_knowledge is not None:
            return bool(override.user_knowledge)
        fm = self.load_agent_frontmatter(agent_name)
        if fm is not None and "user_knowledge" in fm:
            raw = fm.get("user_knowledge")
            if isinstance(raw, bool):
                return raw
            if isinstance(raw, str):
                return raw.strip().lower() in {"1", "true", "yes", "on"}
        return agent_name in _USER_KNOWLEDGE_DEFAULT_ON

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

    def _read_agent_file(self, agent_name: str) -> str:
        path = os.path.join(self._config_dir, "agents", f"{agent_name}.md")
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Agent definition not found: {path}")

        with open(path) as f:
            return f.read()

    def load_agent(self, agent_name: str) -> str:
        """Return the agent definition body (frontmatter stripped).

        If an override provides ``system_prompt_override`` or
        ``body_override`` it wins. Standalone overrides (no baseline .md)
        must supply one of them.
        """
        override = self._get_override(agent_name)
        if override is not None and override.system_prompt_override:
            return override.system_prompt_override

        baseline_body: str | None = None
        try:
            raw = self._read_agent_file(agent_name)
            _, baseline_body = _split_frontmatter(raw)
        except FileNotFoundError:
            baseline_body = None

        if override is not None and override.body_override is not None:
            return override.body_override
        if baseline_body is not None:
            return baseline_body
        if override is not None:
            # Standalone override with no body — return empty body rather
            # than raise. Callers should have set a body_override.
            return ""
        raise FileNotFoundError(
            f"Agent definition not found: {agent_name}"
        )

    def load_agent_frontmatter(
        self, agent_name: str
    ) -> dict[str, Any] | None:
        """Return parsed YAML frontmatter dict for an agent, or None.

        Standalone overrides with no baseline file return ``None``.
        """
        try:
            raw = self._read_agent_file(agent_name)
        except FileNotFoundError:
            return None
        fm, _ = _split_frontmatter(raw)
        return fm

    def load_agent_heartbeat_config(
        self, agent_name: str
    ) -> HeartbeatConfig | None:
        """Return the HeartbeatConfig for an agent, or None if not set."""
        override = self._get_override(agent_name)
        if override is not None and override.heartbeat is not None:
            return override.heartbeat
        fm = self.load_agent_frontmatter(agent_name)
        if not fm:
            return None
        hb = fm.get("heartbeat")
        if hb is None:
            return None
        if not isinstance(hb, dict):
            raise ValueError(
                f"agent {agent_name!r} heartbeat frontmatter must be a "
                f"mapping, got {type(hb).__name__}"
            )
        return HeartbeatConfig(**hb)

    def load_agent_model_ref(
        self, agent_name: str
    ) -> AgentModelRef | None:
        """Return the ``model:`` frontmatter reference, or None if absent.

        Accepts:
          - ``model: "ProviderName/model_id"`` (string)
          - ``model: "bare-model-id"`` (string)
          - ``model: {name: "...", params: {...}}`` (mapping)
        """
        override = self._get_override(agent_name)
        if override is not None and override.model.primary:
            params = None
            if override.model.params:
                try:
                    params = ModelParams(**override.model.params)
                except Exception:
                    params = None
            return AgentModelRef(name=override.model.primary, params=params)
        fm = self.load_agent_frontmatter(agent_name)
        if not fm:
            return None
        raw = fm.get("model")
        if raw is None:
            return None
        if isinstance(raw, str):
            return AgentModelRef(name=raw)
        if isinstance(raw, dict):
            name = raw.get("name")
            if not isinstance(name, str) or not name:
                raise ValueError(
                    f"agent {agent_name!r} model frontmatter must include a "
                    f"string 'name'"
                )
            params_raw = raw.get("params")
            params: ModelParams | None = None
            if params_raw is not None:
                if not isinstance(params_raw, dict):
                    raise ValueError(
                        f"agent {agent_name!r} model.params must be a "
                        f"mapping, got {type(params_raw).__name__}"
                    )
                params = ModelParams(**params_raw)
            return AgentModelRef(name=name, params=params)
        raise ValueError(
            f"agent {agent_name!r} model frontmatter must be a string or "
            f"mapping, got {type(raw).__name__}"
        )

    def build_system_prompt(
        self,
        agent_name: str,
        soul_base: str = "base",
        soul_overlay: str | None = None,
        memories: list[str] | None = None,
        skills: list[Skill] | None = None,
    ) -> str:
        parts: list[str] = []

        # Agent definition (frontmatter stripped)
        agent_def = self.load_agent(agent_name)
        parts.append(f"# Agent Role\n\n{agent_def}")

        # Current time — injected on every build so the agent never has
        # to guess "what time is it" or silently assume UTC.
        parts.append(f"# Current time\n\n{self.current_time_block()}")

        # User profile — shared context about who the user is. Only
        # injected for agents whose resolved ``user_knowledge`` flag is
        # True (orchestrator + profile-mgr by default; everyone else
        # opt-in via agent frontmatter or Firestore override). Agents
        # that don't need personal context stay lean.
        if self.resolve_user_knowledge(agent_name):
            user_profile = self.load_user_profile()
            if user_profile:
                parts.append(f"# About the User\n\n{user_profile}")
            else:
                parts.append(
                    "# About the User\n\n"
                    "The user's profile is blank — we don't know them yet. "
                    "If this is the orchestrator or profile-mgr: gently "
                    "offer to run onboarding so we can fill it in. "
                    "Otherwise: proceed without assuming anything personal."
                )

        # Soul — agent-specific personality / behavior, distinct from user
        # context.
        try:
            soul = self.load_soul(soul_base, overlay=soul_overlay)
        except FileNotFoundError:
            # Standalone agents may be created without a matching soul
            # base/overlay file — degrade to an empty soul rather than crash.
            soul = ""
        # Override-provided raw soul overlay markdown is appended verbatim.
        override = self._get_override(agent_name)
        if override is not None and override.soul_overlay:
            if soul:
                soul = soul + "\n" + override.soul_overlay
            else:
                soul = override.soul_overlay
        parts.append(f"# Personality\n\n{soul}")

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
