"""OpenClaw → GClaw importer CLI.

Usage:
  uv run python -m gclaw.migrate.openclaw_import \\
    --source /path/to/openclaw-import \\
    [--apply] [--skip-providers] [--skip-agents] [--skip-context]

Default is dry-run. Pass ``--apply`` to actually write to Firestore.

The source directory is expected to contain:

  - ``openclaw.json`` — the OpenClaw config
  - ``shared-context/`` — namespaced markdown (and some other files)
  - ``workspaces/workspace-<agent>/`` — optional per-agent overlay files
    (AGENTS.md, SOUL.md, IDENTITY.md, USER.md). Missing workspaces are
    reported as gaps; re-running the importer once they arrive will fill
    body_override / soul_overlay on the existing override.

The importer is idempotent: providers/models/agents already present are
updated rather than re-created.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from gclaw.catalog.presets import PRESETS
from gclaw.models.agent_config import ThinkingLevel
from gclaw.models.catalog import (
    ApiKeyKind,
    ApiKeySpec,
    Capabilities,
    ModelParams,
    ProviderKind,
)

logger = logging.getLogger(__name__)


# --- Provider prefix mapping -------------------------------------------------


# ``provider prefix`` → (ProviderKind, display_name, env_var_for_api_key)
_PROVIDER_MAP: dict[str, tuple[ProviderKind, str, str | None]] = {
    "anthropic": (ProviderKind.ANTHROPIC, "Anthropic", "ANTHROPIC_API_KEY"),
    "openai": (ProviderKind.OPENAI, "OpenAI", "OPENAI_API_KEY"),
    "google": (ProviderKind.GOOGLE_GEMINI, "Google Gemini", "GOOGLE_API_KEY"),
    "openrouter": (ProviderKind.OPENROUTER, "OpenRouter", "OPENROUTER_API_KEY"),
    "groq": (ProviderKind.GROQ, "Groq", "GROQ_API_KEY"),
    "together": (ProviderKind.TOGETHER, "Together", "TOGETHER_API_KEY"),
    "github-copilot": (
        ProviderKind.CUSTOM_OPENAI,
        "GitHub Copilot",
        "GITHUB_COPILOT_TOKEN",
    ),
}


def _classify_provider(prefix: str) -> tuple[ProviderKind, str, str | None]:
    """Return (kind, display_name, env_var) for an OpenClaw provider prefix."""
    if prefix in _PROVIDER_MAP:
        return _PROVIDER_MAP[prefix]
    if prefix == "ollama" or prefix.startswith("ollama"):
        return ProviderKind.OLLAMA, "Ollama", None
    if prefix.startswith("custom-"):
        # e.g. ``custom-generativelanguage-googleapis-com`` → display name
        # "Custom generativelanguage.googleapis.com"
        remainder = prefix.removeprefix("custom-")
        display = "Custom " + remainder.replace("-", ".")
        return ProviderKind.CUSTOM_OPENAI, display, None
    # Unknown vendor — best effort.
    return ProviderKind.CUSTOM_OPENAI, prefix.title(), None


def _default_base_url(prefix: str, kind: ProviderKind) -> str | None:
    """Static default base URL for a prefix (before consulting the JSON)."""
    if prefix == "github-copilot":
        return "https://api.githubcopilot.com"
    if prefix.startswith("ollama"):
        return "http://localhost:11434"
    if prefix.startswith("custom-"):
        host = prefix.removeprefix("custom-").replace("-", ".")
        return f"https://{host}"
    presets = PRESETS.get(kind)
    if presets:
        return presets.get("base_url_default")
    return None


def _preset_model_info(kind: ProviderKind, model_id: str) -> dict[str, Any] | None:
    """Return preset metadata (context_window, capabilities, etc.) when known."""
    presets = PRESETS.get(kind)
    if not presets:
        return None
    for entry in presets.get("models", []):
        if entry.get("model_id") == model_id:
            return entry
    return None


# --- OpenClaw parsing --------------------------------------------------------


def _split_ref(ref: str) -> tuple[str, str]:
    """Split ``provider/model_id`` → (prefix, model_id). Handles bare refs."""
    if "/" not in ref:
        return ("unknown", ref)
    prefix, _, model_id = ref.partition("/")
    return (prefix, model_id)


def _collect_model_refs(config: dict) -> list[str]:
    """Collect every unique ``provider/model_id`` reference in the config."""
    refs: set[str] = set()
    agents = config.get("agents", {}) or {}
    defaults = agents.get("defaults", {}) or {}
    model_section = defaults.get("model") or {}
    if isinstance(model_section, str):
        refs.add(model_section)
    elif isinstance(model_section, dict):
        primary = model_section.get("primary")
        if primary:
            refs.add(primary)
        for fb in model_section.get("fallbacks", []) or []:
            refs.add(fb)
    for ref in (defaults.get("models") or {}).keys():
        refs.add(ref)
    for agent in agents.get("list", []) or []:
        model = agent.get("model")
        if isinstance(model, str):
            refs.add(model)
        elif isinstance(model, dict):
            p = model.get("primary")
            if p:
                refs.add(p)
            for fb in model.get("fallbacks", []) or []:
                refs.add(fb)
    return sorted(refs)


def _normalize_model_spec(value: Any) -> tuple[str | None, list[str]]:
    """Turn an agent.model (str | {primary,fallbacks} | None) into (primary, fallbacks)."""
    if value is None:
        return (None, [])
    if isinstance(value, str):
        return (value, [])
    if isinstance(value, dict):
        return (value.get("primary"), list(value.get("fallbacks") or []))
    return (None, [])


def _merge_tools(
    defaults: dict | None, agent: dict | None
) -> dict[str, Any]:
    """Merge defaults.tools with agent.tools. Agent wins on overlap."""
    base_tools = (defaults or {}).get("tools") or {}
    a_tools = (agent or {}).get("tools") or {}
    profile = a_tools.get("profile") or base_tools.get("profile")
    # alsoAllow in OpenClaw is additive; treat it as allow-list union.
    allow = list(
        dict.fromkeys(
            list(base_tools.get("alsoAllow") or [])
            + list(a_tools.get("alsoAllow") or [])
        )
    )
    deny = list(
        dict.fromkeys(
            list(base_tools.get("deny") or [])
            + list(a_tools.get("deny") or [])
        )
    )
    return {"profile": profile, "allow": allow, "deny": deny}


def _merge_heartbeat(
    defaults: dict | None, agent: dict | None
) -> dict | None:
    """Merge defaults.heartbeat with agent.heartbeat. Returns normalized dict."""
    dh = (defaults or {}).get("heartbeat") or {}
    ah = (agent or {}).get("heartbeat") or {}
    if not dh and not ah:
        return None
    merged = {**dh, **ah}
    return merged


def _heartbeat_to_config(raw: dict | None) -> dict | None:
    """Translate an OpenClaw heartbeat dict into a HeartbeatConfig-shaped dict."""
    if not raw:
        return None
    target_raw = (raw.get("target") or "").lower()
    target = "none"
    channel = None
    if target_raw in ("slack", "discord", "whatsapp", "telegram"):
        target = "channel"
        channel = target_raw
    elif target_raw == "last":
        target = "last"
    out = {
        "enabled": True,
        "every": raw.get("every") or "30m",
        "target": target,
        "channel": channel,
        "prompt": raw.get("prompt"),
    }
    return {k: v for k, v in out.items() if v is not None or k in ("enabled",)}


def _thinking_level(raw: str | None) -> str | None:
    if raw is None:
        return None
    s = raw.strip().lower()
    try:
        return ThinkingLevel(s).value
    except ValueError:
        return None


# --- Shared-context walker ---------------------------------------------------


_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def _parse_timestamp_from_name(name: str) -> datetime | None:
    m = _DATE_RE.match(name)
    if not m:
        return None
    try:
        return datetime(
            int(m.group(1)), int(m.group(2)), int(m.group(3)),
            tzinfo=timezone.utc,
        )
    except ValueError:
        return None


def _rel_namespace(root: Path, path: Path) -> str:
    rel = path.parent.relative_to(root)
    parts = [p for p in rel.parts if p not in ("", ".")]
    if not parts:
        return "root"
    return ":".join(parts)


# --- Plan dataclasses -------------------------------------------------------


@dataclass
class ProviderPlan:
    prefix: str
    kind: ProviderKind
    display_name: str
    base_url: str | None
    api_key: ApiKeySpec | None
    notes: str = ""
    already_present: bool = False


@dataclass
class ModelPlan:
    provider_prefix: str
    provider_display_name: str
    model_id: str
    display_name: str
    params: dict[str, Any]
    context_window: int | None = None
    capabilities: dict[str, bool] = field(default_factory=dict)
    already_present: bool = False


@dataclass
class AgentPlan:
    agent_name: str
    display_name: str
    model_primary: str | None
    model_fallbacks: list[str]
    thinking: str | None
    tools: dict[str, Any]
    heartbeat: dict | None
    subagents_allow: list[str] | None
    body_override: str | None
    soul_overlay: str | None
    missing_workspace: bool
    already_present: bool = False
    is_orchestrator: bool = False  # mapped from OpenClaw 'main'


@dataclass
class ContextPlan:
    namespace: str
    path: Path
    created_by: str
    timestamp: datetime
    expires_at: datetime
    mime: str


@dataclass
class ImportPlan:
    providers: list[ProviderPlan] = field(default_factory=list)
    models: list[ModelPlan] = field(default_factory=list)
    agents: list[AgentPlan] = field(default_factory=list)
    context_entries: list[ContextPlan] = field(default_factory=list)
    skipped_binaries: list[Path] = field(default_factory=list)
    missing_workspaces: list[str] = field(default_factory=list)
    unknown_tools: list[str] = field(default_factory=list)


# --- Plan builders -----------------------------------------------------------


def _workspace_files_for(source: Path, agent_id: str) -> tuple[str | None, str | None]:
    """Return (body_override, soul_overlay) from workspace-<id>/ if present."""
    ws = source / "workspaces" / f"workspace-{agent_id}"
    if not ws.is_dir():
        return (None, None)
    body_parts: list[str] = []
    soul_parts: list[str] = []
    for fname in ("AGENTS.md", "IDENTITY.md", "USER.md"):
        fp = ws / fname
        if fp.is_file():
            body_parts.append(f"# {fname}\n\n{fp.read_text()}")
    for fname in ("SOUL.md",):
        fp = ws / fname
        if fp.is_file():
            soul_parts.append(fp.read_text())
    body = "\n\n".join(body_parts) if body_parts else None
    soul = "\n\n".join(soul_parts) if soul_parts else None
    return (body, soul)


#: Map env-var fallback → canonical Secret Manager secret name
_ENV_TO_SM: dict[str, str] = {
    "ANTHROPIC_API_KEY": "gclaw-anthropic-api-key",
    "OPENAI_API_KEY": "gclaw-openai-api-key",
    "GOOGLE_API_KEY": "gclaw-google-api-key",
    "OPENROUTER_API_KEY": "gclaw-openrouter-api-key",
    "GROQ_API_KEY": "gclaw-groq-api-key",
    "TOGETHER_API_KEY": "gclaw-together-api-key",
    "GITHUB_COPILOT_TOKEN": "gclaw-github-copilot-token",
    "PERPLEXITY_API_KEY": "gclaw-perplexity-api-key",
    "SLACK_BOT_TOKEN": "gclaw-slack-bot-token",
    "SLACK_APP_TOKEN": "gclaw-slack-app-token",
    "DISCORD_BOT_TOKEN": "gclaw-discord-bot-token",
}


def _sm_api_key(env_name: str | None, *, project: str) -> ApiKeySpec | None:
    """Return a Secret-Manager ApiKeySpec for the given env-var alias, or None."""
    if not env_name:
        return None
    sm_name = _ENV_TO_SM.get(env_name)
    if not sm_name:
        return None
    return ApiKeySpec(
        kind=ApiKeyKind.SECRET_MANAGER,
        value=f"projects/{project}/secrets/{sm_name}/versions/latest",
    )


def build_plan(
    source: Path,
    *,
    existing_provider_names: set[str] | None = None,
    existing_model_keys: set[tuple[str, str]] | None = None,
    existing_agent_names: set[str] | None = None,
    skip_providers: bool = False,
    skip_agents: bool = False,
    skip_context: bool = False,
    use_secret_manager: bool = False,
    sm_project: str = "apex-internal-apps",
) -> ImportPlan:
    """Parse the OpenClaw source tree and return a full import plan.

    ``existing_*`` sets let the caller mark entries that are already
    present so the plan's "create vs update" distinction stays accurate.
    """
    existing_provider_names = existing_provider_names or set()
    existing_model_keys = existing_model_keys or set()
    existing_agent_names = existing_agent_names or set()

    plan = ImportPlan()
    config_path = source / "openclaw.json"
    if not config_path.is_file():
        raise FileNotFoundError(f"openclaw.json not found at {config_path}")

    config = json.loads(config_path.read_text())
    agents_section = config.get("agents", {}) or {}
    defaults = agents_section.get("defaults", {}) or {}
    openclaw_providers = (config.get("models", {}) or {}).get("providers", {}) or {}
    defaults_models = defaults.get("models") or {}

    # ------- Providers & Models -------
    if not skip_providers:
        refs = _collect_model_refs(config)
        prefix_to_models: dict[str, list[str]] = {}
        for ref in refs:
            prefix, model_id = _split_ref(ref)
            prefix_to_models.setdefault(prefix, []).append(model_id)

        prefix_plans: dict[str, ProviderPlan] = {}
        for prefix, model_ids in sorted(prefix_to_models.items()):
            kind, display, env = _classify_provider(prefix)
            base_url = _default_base_url(prefix, kind)
            notes = ""
            # OpenClaw may carry a custom baseUrl under models.providers[prefix]
            cp = openclaw_providers.get(prefix) or {}
            if cp.get("baseUrl"):
                base_url = cp["baseUrl"]
            if use_secret_manager:
                api_key = _sm_api_key(env, project=sm_project)
            else:
                api_key = (
                    ApiKeySpec(kind=ApiKeyKind.ENV, value=env) if env else None
                )
            if kind == ProviderKind.CUSTOM_OPENAI and not env and prefix.startswith("custom-"):
                notes = "Custom OpenAI-compatible endpoint — set API key manually."
            if prefix not in _PROVIDER_MAP and not prefix.startswith(
                ("ollama", "custom-")
            ):
                notes = (notes + " TODO: unrecognized provider prefix.").strip()
            pp = ProviderPlan(
                prefix=prefix,
                kind=kind,
                display_name=display,
                base_url=base_url,
                api_key=api_key,
                notes=notes,
                already_present=(display in existing_provider_names),
            )
            prefix_plans[prefix] = pp
            plan.providers.append(pp)

            for model_id in sorted(set(model_ids)):
                # alias / params from defaults.models[ref]
                ref_key = f"{prefix}/{model_id}"
                spec = defaults_models.get(ref_key) or {}
                alias = spec.get("alias")
                display_model = alias or model_id
                params = spec.get("params") or {}
                preset = _preset_model_info(kind, model_id) or {}
                # Also consult openclaw models.providers[prefix].models[]
                for cm in cp.get("models", []) or []:
                    if cm.get("id") == model_id:
                        preset = {
                            **preset,
                            "context_window": cm.get("contextWindow")
                            or preset.get("context_window"),
                            "max_output_tokens": cm.get("maxTokens")
                            or preset.get("max_output_tokens"),
                        }
                        break
                mp = ModelPlan(
                    provider_prefix=prefix,
                    provider_display_name=display,
                    model_id=model_id,
                    display_name=display_model,
                    params=params,
                    context_window=preset.get("context_window"),
                    capabilities=preset.get("capabilities") or {},
                    already_present=((display, model_id) in existing_model_keys),
                )
                plan.models.append(mp)

    # ------- Agents -------
    if not skip_agents:
        for agent in agents_section.get("list", []) or []:
            agent_id = agent.get("id")
            if not agent_id:
                continue
            is_main = bool(agent.get("default")) or agent_id == "main"
            target_name = "orchestrator" if is_main else agent_id

            primary, fallbacks = _normalize_model_spec(agent.get("model"))
            if primary is None:
                d_primary, d_fb = _normalize_model_spec(defaults.get("model"))
                primary = d_primary
                if not fallbacks:
                    fallbacks = d_fb

            tools = _merge_tools(defaults, agent)
            hb_raw = _merge_heartbeat(defaults, agent)
            hb = _heartbeat_to_config(hb_raw)

            sub = agent.get("subagents") or {}
            allow = sub.get("allowAgents")
            if allow is None:
                subagents_allow = None
            elif allow == ["*"]:
                subagents_allow = ["*"]
            else:
                subagents_allow = list(allow)

            thinking = _thinking_level(
                agent.get("thinking") or defaults.get("thinkingDefault")
            )

            body, soul = _workspace_files_for(source, agent_id)
            missing_ws = body is None and soul is None

            identity = agent.get("identity") or {}
            display_name = (
                identity.get("name") or agent.get("name") or agent_id
            )

            ap = AgentPlan(
                agent_name=target_name,
                display_name=display_name,
                model_primary=primary,
                model_fallbacks=fallbacks,
                thinking=thinking,
                tools=tools,
                heartbeat=hb,
                subagents_allow=subagents_allow,
                body_override=body,
                soul_overlay=soul,
                missing_workspace=missing_ws,
                already_present=(target_name in existing_agent_names),
                is_orchestrator=is_main,
            )
            plan.agents.append(ap)
            if missing_ws:
                plan.missing_workspaces.append(target_name)

        # Identify tools referenced in OpenClaw that are not implemented
        # here. Heuristic: look at defaults.tools.alsoAllow + each agent's
        # alsoAllow.
        seen_tools: set[str] = set()
        for src in (defaults, *(agents_section.get("list", []) or [])):
            for t in ((src.get("tools") or {}).get("alsoAllow") or []):
                seen_tools.add(t)
        known_tools = {
            "agents_list", "memory_read", "memory_write",
            "context_read", "context_write",
        }
        plan.unknown_tools = sorted(seen_tools - known_tools)

    # ------- Shared context -------
    if not skip_context:
        ctx_root = source / "shared-context"
        if ctx_root.is_dir():
            for path in sorted(ctx_root.rglob("*")):
                if not path.is_file():
                    continue
                rel = path.relative_to(ctx_root)
                # Skip hidden dotfiles / .git / .gitkeep
                if any(part.startswith(".") for part in rel.parts):
                    continue
                if path.suffix.lower() != ".md":
                    plan.skipped_binaries.append(path)
                    continue
                ns = _rel_namespace(ctx_root, path)
                ts = _parse_timestamp_from_name(path.name)
                if ts is None:
                    try:
                        ts = datetime.fromtimestamp(
                            path.stat().st_mtime, tz=timezone.utc
                        )
                    except OSError:
                        ts = datetime.now(timezone.utc)
                expires_at = ts + timedelta(days=30)
                plan.context_entries.append(
                    ContextPlan(
                        namespace=ns,
                        path=path,
                        created_by="openclaw-import",
                        timestamp=ts,
                        expires_at=expires_at,
                        mime="text/markdown",
                    )
                )

    return plan


# --- Plan printing -----------------------------------------------------------


def _summarize_context(
    entries: list[ContextPlan],
) -> list[tuple[str, int]]:
    by_ns: dict[str, int] = {}
    for e in entries:
        by_ns[e.namespace] = by_ns.get(e.namespace, 0) + 1
    return sorted(by_ns.items(), key=lambda x: (-x[1], x[0]))


def render_plan(plan: ImportPlan) -> str:
    lines: list[str] = []
    lines.append("OpenClaw import plan")
    lines.append("─" * 20)

    to_create_p = [p for p in plan.providers if not p.already_present]
    present_p = [p for p in plan.providers if p.already_present]
    lines.append(f"Providers to create: {len(to_create_p)}")
    for p in to_create_p:
        note = ""
        if p.api_key and p.api_key.kind == ApiKeyKind.ENV:
            note = f" (env {p.api_key.value} expected)"
        elif p.api_key and p.api_key.kind == ApiKeyKind.SECRET_MANAGER:
            note = f" (sm {p.api_key.value})"
        elif p.api_key is None:
            note = " (no api key)"
        if p.notes:
            note += f" [{p.notes}]"
        lines.append(
            f"  - {p.display_name} [{p.kind.value}]"
            f"{(' base=' + p.base_url) if p.base_url else ''}{note}"
        )
    lines.append(f"Providers already present: {len(present_p)}")

    to_create_m = [m for m in plan.models if not m.already_present]
    present_m = [m for m in plan.models if m.already_present]
    lines.append(f"Models to create: {len(to_create_m)}")
    for m in to_create_m:
        lines.append(
            f"  - {m.provider_display_name}/{m.model_id}"
            f"{(' (' + m.display_name + ')') if m.display_name != m.model_id else ''}"
        )
    lines.append(f"Models already present: {len(present_m)}")

    to_create_a = [a for a in plan.agents if not a.already_present]
    present_a = [a for a in plan.agents if a.already_present]
    lines.append(f"Agents to create: {len(to_create_a)}")
    for a in to_create_a:
        bits = []
        if a.is_orchestrator:
            bits.append("→ orchestrator")
        if a.heartbeat and a.heartbeat.get("enabled"):
            bits.append(f"hb {a.heartbeat.get('every')}")
        if a.missing_workspace:
            bits.append("missing workspace body")
        suffix = f" ({'; '.join(bits)})" if bits else ""
        lines.append(f"  - {a.agent_name}{suffix}")
    lines.append(f"Agents already present (will update): {len(present_a)}")

    ns_summary = _summarize_context(plan.context_entries)
    lines.append(f"Shared-context namespaces: {len(ns_summary)}")
    for ns, count in ns_summary:
        lines.append(f"  - {ns}: {count} entries")
    lines.append(
        f"Total shared-context entries: {len(plan.context_entries)}"
    )
    if plan.skipped_binaries:
        lines.append(
            f"Shared-context binaries skipped: {len(plan.skipped_binaries)}"
        )

    lines.append("Gaps to address manually:")
    if plan.missing_workspaces:
        lines.append(
            "  - Workspaces not yet copied for: "
            + ", ".join(plan.missing_workspaces)
            + " (will pick up on re-run)"
        )
    if plan.unknown_tools:
        lines.append(
            "  - Tools referenced but not implemented in GClaw: "
            + ", ".join(plan.unknown_tools)
        )
    if plan.skipped_binaries:
        sample = ", ".join(p.name for p in plan.skipped_binaries[:5])
        more = (
            f" (+{len(plan.skipped_binaries) - 5} more)"
            if len(plan.skipped_binaries) > 5
            else ""
        )
        lines.append(
            f"  - Binary shared-context files skipped (upload manually): {sample}{more}"
        )
    if not (plan.missing_workspaces or plan.unknown_tools or plan.skipped_binaries):
        lines.append("  - (none)")

    lines.append("Skills: 0 to import (OpenClaw skills list not migrated)")
    lines.append("Channels: 0 to import (not wired in this pass)")
    lines.append("")
    lines.append("Run with --apply to execute.")
    return "\n".join(lines)


# --- Apply -------------------------------------------------------------------


@dataclass
class ApplyResult:
    providers_created: int = 0
    providers_updated: int = 0
    models_created: int = 0
    models_updated: int = 0
    agents_created: int = 0
    agents_updated: int = 0
    context_created: int = 0
    errors: list[str] = field(default_factory=list)


def apply_plan(
    plan: ImportPlan,
    *,
    catalog_service,
    agent_config_service,
    shared_context_service,
    skip_providers: bool = False,
    skip_agents: bool = False,
    skip_context: bool = False,
) -> ApplyResult:
    result = ApplyResult()

    # -- providers
    provider_id_by_display: dict[str, str] = {}
    if not skip_providers and catalog_service is not None:
        existing_providers = {p.name: p for p in catalog_service.list_providers()}
        for pp in plan.providers:
            try:
                existing = existing_providers.get(pp.display_name)
                if existing is None:
                    provider = catalog_service.create_provider(
                        name=pp.display_name,
                        kind=pp.kind,
                        base_url=pp.base_url,
                        api_key=pp.api_key,
                    )
                    result.providers_created += 1
                else:
                    updates: dict[str, Any] = {}
                    if pp.base_url and existing.base_url != pp.base_url:
                        updates["base_url"] = pp.base_url
                    if pp.api_key and existing.api_key is None:
                        updates["api_key"] = pp.api_key
                    if updates:
                        provider = catalog_service.update_provider(
                            existing.id, **updates
                        )
                        result.providers_updated += 1
                    else:
                        provider = existing
                provider_id_by_display[pp.display_name] = provider.id
            except Exception as e:
                result.errors.append(f"provider {pp.display_name}: {e}")

        # -- models
        existing_models_by_key: dict[tuple[str, str], Any] = {}
        for m in catalog_service.list_models():
            existing_models_by_key[(m.provider_id, m.model_id)] = m

        for mp in plan.models:
            try:
                provider_id = provider_id_by_display.get(mp.provider_display_name)
                if provider_id is None:
                    result.errors.append(
                        f"model {mp.model_id}: no provider id for {mp.provider_display_name}"
                    )
                    continue
                key = (provider_id, mp.model_id)
                params = ModelParams(**{k: v for k, v in mp.params.items() if k in {
                    "temperature", "top_p", "max_tokens", "thinking_budget"
                }}) if mp.params else ModelParams()
                caps = Capabilities(**mp.capabilities) if mp.capabilities else Capabilities()
                if key not in existing_models_by_key:
                    catalog_service.create_model(
                        provider_id=provider_id,
                        model_id=mp.model_id,
                        display_name=mp.display_name,
                        context_window=mp.context_window,
                        capabilities=caps,
                        params=params,
                    )
                    result.models_created += 1
                else:
                    existing_model = existing_models_by_key[key]
                    catalog_service.update_model(
                        existing_model.id,
                        display_name=mp.display_name,
                        context_window=mp.context_window or existing_model.context_window,
                    )
                    result.models_updated += 1
            except Exception as e:
                result.errors.append(f"model {mp.model_id}: {e}")

    # -- agents
    if not skip_agents and agent_config_service is not None:
        existing_names = {a["name"] for a in agent_config_service.list_agents()}
        for ap in plan.agents:
            try:
                patch: dict[str, Any] = {
                    "identity": {"display_name": ap.display_name},
                    "model": {
                        "primary": ap.model_primary,
                        "fallbacks": ap.model_fallbacks,
                        "thinking": ap.thinking,
                    },
                    "tools": {
                        "profile": ap.tools.get("profile"),
                        "allow": ap.tools.get("allow") or [],
                        "deny": ap.tools.get("deny") or [],
                    },
                    "subagents": {"allow": ap.subagents_allow},
                }
                if ap.heartbeat is not None:
                    patch["heartbeat"] = ap.heartbeat
                if ap.body_override is not None:
                    patch["body_override"] = ap.body_override
                if ap.soul_overlay is not None:
                    patch["soul_overlay"] = ap.soul_overlay

                if ap.agent_name in existing_names:
                    agent_config_service.upsert_override(ap.agent_name, patch)
                    result.agents_updated += 1
                else:
                    # For orchestrator or any agent that has a baseline .md,
                    # use upsert_override; else create standalone.
                    has_baseline = False
                    try:
                        has_baseline = (
                            agent_config_service.read_baseline(ap.agent_name)
                            is not None
                        )
                    except Exception:
                        has_baseline = False

                    if has_baseline or ap.is_orchestrator:
                        agent_config_service.upsert_override(ap.agent_name, patch)
                        result.agents_updated += 1
                    else:
                        body = ap.body_override or (
                            f"# {ap.display_name}\n\n"
                            f"Imported from OpenClaw. Workspace body not yet "
                            f"present — re-run the importer once "
                            f"`workspaces/workspace-{ap.agent_name}/AGENTS.md` "
                            f"is copied over.\n"
                        )
                        agent_config_service.create_standalone(
                            agent_name=ap.agent_name,
                            body=body,
                            display_name=ap.display_name,
                            model_primary=ap.model_primary,
                            soul_overlay=ap.soul_overlay,
                        )
                        # Apply the rest of the spec (tools/heartbeat/etc.)
                        # as a follow-up patch.
                        agent_config_service.upsert_override(ap.agent_name, patch)
                        result.agents_created += 1
            except Exception as e:
                result.errors.append(f"agent {ap.agent_name}: {e}")

    # -- context
    if not skip_context and shared_context_service is not None:
        for cp in plan.context_entries:
            try:
                content = cp.path.read_text(encoding="utf-8", errors="replace")
                shared_context_service.write_text(
                    namespace=cp.namespace,
                    content=content,
                    created_by=cp.created_by,
                    metadata={
                        "source": "openclaw-import",
                        "source_path": str(cp.path.name),
                        "timestamp": cp.timestamp.isoformat(),
                        "expires_at": cp.expires_at.isoformat(),
                    },
                    mime=cp.mime,
                )
                result.context_created += 1
            except Exception as e:
                result.errors.append(
                    f"context {cp.path.name} → {cp.namespace}: {e}"
                )

    return result


def render_apply(result: ApplyResult) -> str:
    lines = ["OpenClaw import — applied"]
    lines.append("─" * 24)
    lines.append(
        f"Providers: {result.providers_created} created, "
        f"{result.providers_updated} updated"
    )
    lines.append(
        f"Models: {result.models_created} created, "
        f"{result.models_updated} updated"
    )
    lines.append(
        f"Agents: {result.agents_created} created, "
        f"{result.agents_updated} updated"
    )
    lines.append(f"Shared-context entries: {result.context_created} created")
    if result.errors:
        lines.append(f"Errors ({len(result.errors)}):")
        for e in result.errors[:50]:
            lines.append(f"  - {e}")
    return "\n".join(lines)


# --- Service wiring ----------------------------------------------------------


def _build_services() -> dict[str, Any]:
    """Build the services needed by --apply, same wiring as main.build_app."""
    from gclaw.catalog.service import CatalogService
    from gclaw.config.agent_config_service import AgentConfigService
    from gclaw.config.loader import ConfigLoader
    from gclaw.firestore.agent_override_repo import AgentOverrideRepo
    from gclaw.firestore.catalog_repo import ModelRepo, ProviderRepo
    from gclaw.firestore.client import get_firestore_client
    from gclaw.firestore.context_entry_repo import ContextEntryRepo
    from gclaw.settings import get_settings
    from gclaw.shared_context.blob_store import BlobStore
    from gclaw.shared_context.service import SharedContextService
    from gclaw.skill.in_memory_repo import InMemorySkillRepo
    from gclaw.skill.loader import SkillLoader
    from gclaw.skill.registry import SkillRegistry

    settings = get_settings()
    db = get_firestore_client(
        project=settings.gcp_project_id,
        database=settings.firestore_database,
    )

    catalog_service = CatalogService(
        provider_repo=ProviderRepo(db=db),
        model_repo=ModelRepo(db=db),
    )

    skill_loader = SkillLoader()
    loader = ConfigLoader(settings.config_dir, skill_loader=skill_loader)
    skill_registry = SkillRegistry(skill_repo=InMemorySkillRepo())
    try:
        skill_registry.load_builtins(settings.skills_dir)
    except Exception:
        pass

    import os
    agent_config_service = AgentConfigService(
        override_repo=AgentOverrideRepo(db=db),
        loader=loader,
        skill_registry=skill_registry,
        agents_dir=os.path.join(settings.config_dir, "agents"),
    )

    blob_store = None
    try:
        blob_store = BlobStore(
            project=settings.gcp_project_id,
            bucket_name=settings.shared_context_bucket,
        )
    except Exception:
        logger.warning("BlobStore init failed; running index-only")
    shared_context_service = SharedContextService(
        repo=ContextEntryRepo(db=db),
        blob_store=blob_store,
    )

    return {
        "catalog_service": catalog_service,
        "agent_config_service": agent_config_service,
        "shared_context_service": shared_context_service,
    }


def _existing_sets(services: dict[str, Any]) -> tuple[set[str], set[tuple[str, str]], set[str]]:
    """Snapshot of currently-present providers/models/agents for idempotency."""
    catalog = services.get("catalog_service")
    agent_cfg = services.get("agent_config_service")
    provider_names: set[str] = set()
    model_keys: set[tuple[str, str]] = set()
    agent_names: set[str] = set()
    if catalog is not None:
        providers = catalog.list_providers()
        id_to_name = {p.id: p.name for p in providers}
        provider_names = set(id_to_name.values())
        for m in catalog.list_models():
            model_keys.add((id_to_name.get(m.provider_id, ""), m.model_id))
    if agent_cfg is not None:
        try:
            agent_names = {a["name"] for a in agent_cfg.list_agents()}
        except Exception:
            pass
    return provider_names, model_keys, agent_names


# --- CLI ---------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="OpenClaw export root")
    parser.add_argument("--apply", action="store_true", help="Actually write")
    parser.add_argument("--skip-providers", action="store_true")
    parser.add_argument("--skip-agents", action="store_true")
    parser.add_argument("--skip-context", action="store_true")
    parser.add_argument(
        "--use-secret-manager",
        action="store_true",
        help=(
            "Reference Secret Manager paths for provider api keys instead of "
            "env vars. Run `python -m gclaw.migrate.seed_secrets --apply` first."
        ),
    )
    parser.add_argument(
        "--sm-project",
        default="apex-internal-apps",
        help="GCP project for Secret Manager paths (default apex-internal-apps).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    source = Path(args.source).resolve()
    if not source.is_dir():
        print(f"source not found: {source}", file=sys.stderr)
        return 2

    if args.apply:
        services = _build_services()
        prov_names, model_keys, agent_names = _existing_sets(services)
    else:
        services = {}
        prov_names, model_keys, agent_names = set(), set(), set()

    plan = build_plan(
        source,
        existing_provider_names=prov_names,
        existing_model_keys=model_keys,
        existing_agent_names=agent_names,
        skip_providers=args.skip_providers,
        skip_agents=args.skip_agents,
        skip_context=args.skip_context,
        use_secret_manager=args.use_secret_manager,
        sm_project=args.sm_project,
    )

    print(render_plan(plan))

    if not args.apply:
        return 0

    result = apply_plan(
        plan,
        catalog_service=services.get("catalog_service"),
        agent_config_service=services.get("agent_config_service"),
        shared_context_service=services.get("shared_context_service"),
        skip_providers=args.skip_providers,
        skip_agents=args.skip_agents,
        skip_context=args.skip_context,
        use_secret_manager=args.use_secret_manager,
        sm_project=args.sm_project,
    )
    print()
    print(render_apply(result))
    return 0 if not result.errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
