"""Tests for the OpenClaw → GClaw importer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from gclaw.migrate.openclaw_import import (
    ApplyResult,
    CronPlanEntry,
    ImportPlan,
    SkillPlanEntry,
    _build_cron_from_dict,
    _classify_provider,
    _discover_skills,
    _load_crons,
    _schedule_summary,
    _split_ref,
    apply_plan,
    build_plan,
    render_plan,
)
from gclaw.models.catalog import (
    ApiKeyKind,
    Capabilities,
    ModelParams,
    ModelProvider,
    ModelRecord,
    ProviderKind,
)
from gclaw.models.cron import (
    AgentTurnPayload,
    AtSchedule,
    Cron,
    CronExprSchedule,
    SystemEventPayload,
)


# ---- helpers / fakes --------------------------------------------------------


def _write_source(tmp_path: Path, *, with_workspace: bool = False) -> Path:
    """Build a minimal OpenClaw source tree at tmp_path."""
    source = tmp_path / "openclaw-import"
    source.mkdir()
    config = {
        "agents": {
            "defaults": {
                "model": {
                    "primary": "anthropic/claude-sonnet-4-6",
                    "fallbacks": ["github-copilot/gpt-5-mini"],
                },
                "models": {
                    "anthropic/claude-sonnet-4-6": {
                        "alias": "sonnet", "streaming": True,
                    },
                    "github-copilot/gpt-5-mini": {},
                },
                "thinkingDefault": "medium",
                "heartbeat": {"every": "1h", "target": "slack"},
            },
            "list": [
                {
                    "id": "main",
                    "default": True,
                    "identity": {"name": "Watson"},
                    "model": {
                        "primary": "anthropic/claude-sonnet-4-6",
                        "fallbacks": ["github-copilot/gpt-5.2-codex"],
                    },
                    "subagents": {"allowAgents": ["intel"]},
                },
                {
                    "id": "intel",
                    "name": "intel",
                    "model": {
                        "primary": "anthropic/claude-haiku-4-5",
                        "fallbacks": ["github-copilot/gpt-5-mini"],
                    },
                },
            ],
        },
        "models": {"providers": {}},
    }
    (source / "openclaw.json").write_text(json.dumps(config))

    ctx = source / "shared-context"
    (ctx / "feeds").mkdir(parents=True)
    (ctx / "feeds" / "2026-03-11-10.md").write_text("hello feeds")
    (ctx / "research" / "scott").mkdir(parents=True)
    (ctx / "research" / "scott" / "2026-03-12.md").write_text("scott research")
    (ctx / "watson-rss-feed-url.md").write_text("https://example.com/rss")
    # Binary should be skipped
    (ctx / "hook-log").mkdir()
    (ctx / "hook-log" / ".gitkeep").write_text("")
    (ctx / "knowledge-base").mkdir()
    (ctx / "knowledge-base" / "entries.json").write_text("{}")

    if with_workspace:
        ws = source / "workspaces" / "workspace-intel"
        ws.mkdir(parents=True)
        (ws / "AGENTS.md").write_text("# Intel agent body")
        (ws / "SOUL.md").write_text("# Intel soul")

    return source


class FakeCatalog:
    def __init__(self) -> None:
        self.providers: list[ModelProvider] = []
        self.models: list[ModelRecord] = []
        self.create_provider_calls: list[dict] = []
        self.create_model_calls: list[dict] = []
        self.update_provider_calls: list[dict] = []
        self.update_model_calls: list[dict] = []

    def list_providers(self):
        return list(self.providers)

    def list_models(self, provider_id=None):
        if provider_id is None:
            return list(self.models)
        return [m for m in self.models if m.provider_id == provider_id]

    def create_provider(self, *, name, kind, base_url=None, api_key=None, **kw):
        p = ModelProvider(name=name, kind=kind, base_url=base_url, api_key=api_key)
        self.providers.append(p)
        self.create_provider_calls.append({"name": name, "kind": kind})
        return p

    def update_provider(self, provider_id, **updates):
        for p in self.providers:
            if p.id == provider_id:
                for k, v in updates.items():
                    setattr(p, k, v)
                self.update_provider_calls.append({"id": provider_id, **updates})
                return p
        raise ValueError("missing")

    def create_model(self, *, provider_id, model_id, display_name, **kw):
        caps = kw.get("capabilities") or Capabilities()
        if isinstance(caps, dict):
            caps = Capabilities(**caps)
        params = kw.get("params") or ModelParams()
        m = ModelRecord(
            provider_id=provider_id,
            model_id=model_id,
            display_name=display_name,
            context_window=kw.get("context_window"),
            capabilities=caps,
            params=params,
        )
        self.models.append(m)
        self.create_model_calls.append(
            {"provider_id": provider_id, "model_id": model_id}
        )
        return m

    def update_model(self, model_id, **updates):
        for m in self.models:
            if m.id == model_id:
                for k, v in updates.items():
                    setattr(m, k, v)
                self.update_model_calls.append({"id": model_id, **updates})
                return m
        raise ValueError("missing")


class FakeAgentConfig:
    def __init__(self) -> None:
        self.overrides: dict[str, dict] = {}
        self.baselines: set[str] = set()
        self.create_standalone_calls: list[dict] = []
        self.upsert_calls: list[dict] = []

    def list_agents(self):
        return [{"name": n} for n in self.overrides.keys()]

    def read_baseline(self, name):
        return "# baseline" if name in self.baselines else None

    def create_standalone(self, *, agent_name, body, **kw):
        self.create_standalone_calls.append(
            {"agent_name": agent_name, "body": body, **kw}
        )
        self.overrides[agent_name] = {
            "body_override": body,
            "identity": {"display_name": kw.get("display_name")},
        }
        return self.overrides[agent_name]

    def upsert_override(self, agent_name, patch):
        self.upsert_calls.append({"agent_name": agent_name, "patch": patch})
        existing = self.overrides.get(agent_name, {})
        existing.update(patch)
        self.overrides[agent_name] = existing
        return existing


class FakeSharedContext:
    def __init__(self) -> None:
        self.writes: list[dict] = []

    def write_text(self, *, namespace, content, created_by, metadata=None, mime="text/markdown"):
        self.writes.append(
            {
                "namespace": namespace,
                "content": content,
                "created_by": created_by,
                "metadata": metadata or {},
                "mime": mime,
            }
        )
        return {"id": f"ctx_{len(self.writes)}"}


# ---- unit-level tests -------------------------------------------------------


def test_split_ref():
    assert _split_ref("anthropic/claude-sonnet-4-6") == (
        "anthropic", "claude-sonnet-4-6"
    )
    assert _split_ref("bareref") == ("unknown", "bareref")


def test_classify_provider_known_vendors():
    assert _classify_provider("anthropic")[0] == ProviderKind.ANTHROPIC
    assert _classify_provider("anthropic-oauth")[0] == ProviderKind.ANTHROPIC_OAUTH
    assert _classify_provider("anthropic-oauth")[1] == "Anthropic (OAuth)"
    assert _classify_provider("anthropic-oauth")[2] is None
    assert _classify_provider("openai")[0] == ProviderKind.OPENAI
    assert _classify_provider("google")[0] == ProviderKind.GOOGLE_GEMINI
    assert _classify_provider("github-copilot")[0] == ProviderKind.CUSTOM_OPENAI
    assert _classify_provider("github-copilot")[2] == "GITHUB_COPILOT_TOKEN"
    assert _classify_provider("ollama-local")[0] == ProviderKind.OLLAMA
    assert _classify_provider("custom-foo-bar-com")[0] == ProviderKind.CUSTOM_OPENAI


# ---- plan-building tests ----------------------------------------------------


def test_build_plan_counts(tmp_path):
    source = _write_source(tmp_path)
    plan = build_plan(source)

    assert len(plan.providers) == 2  # anthropic + github-copilot
    # sonnet, haiku, gpt-5-mini, gpt-5.2-codex
    assert len(plan.models) == 4
    assert len(plan.agents) == 2
    # main → orchestrator rename
    names = [a.agent_name for a in plan.agents]
    assert "orchestrator" in names
    assert "intel" in names
    # 3 markdown files: feeds/..., research/scott/..., watson-rss-feed-url.md
    assert len(plan.context_entries) == 3
    # one binary under knowledge-base (.gitkeep hidden is filtered)
    assert any(p.name == "entries.json" for p in plan.skipped_binaries)


def test_build_plan_namespace_mapping(tmp_path):
    source = _write_source(tmp_path)
    plan = build_plan(source)
    ns = {c.namespace for c in plan.context_entries}
    assert "feeds" in ns
    assert "research:scott" in ns
    assert "root" in ns  # bare file at shared-context root


def test_build_plan_orchestrator_mapping(tmp_path):
    source = _write_source(tmp_path)
    plan = build_plan(source)
    main = next(a for a in plan.agents if a.is_orchestrator)
    assert main.agent_name == "orchestrator"
    assert main.display_name == "Watson"
    assert main.subagents_allow == ["intel"]


def test_build_plan_heartbeat_merge(tmp_path):
    source = _write_source(tmp_path)
    plan = build_plan(source)
    intel = next(a for a in plan.agents if a.agent_name == "intel")
    # defaults give heartbeat 1h/slack → channel target
    assert intel.heartbeat["enabled"] is True
    assert intel.heartbeat["every"] == "1h"
    assert intel.heartbeat["target"] == "channel"
    assert intel.heartbeat["channel"] == "slack"


def test_build_plan_workspace_absent(tmp_path):
    source = _write_source(tmp_path, with_workspace=False)
    plan = build_plan(source)
    for a in plan.agents:
        assert a.body_override is None
        assert a.soul_overlay is None
        assert a.missing_workspace is True


def test_build_plan_workspace_present(tmp_path):
    source = _write_source(tmp_path, with_workspace=True)
    plan = build_plan(source)
    intel = next(a for a in plan.agents if a.agent_name == "intel")
    assert intel.body_override is not None
    assert "Intel agent body" in intel.body_override
    assert intel.soul_overlay is not None
    assert "Intel soul" in intel.soul_overlay
    assert intel.missing_workspace is False


def test_build_plan_model_ref_parsing(tmp_path):
    source = _write_source(tmp_path)
    plan = build_plan(source)
    anthropic = next(p for p in plan.providers if p.prefix == "anthropic")
    assert anthropic.kind == ProviderKind.ANTHROPIC
    sonnet = next(
        m for m in plan.models if m.model_id == "claude-sonnet-4-6"
    )
    assert sonnet.display_name == "sonnet"  # alias wins
    assert sonnet.provider_display_name == "Anthropic"


def test_build_plan_respects_existing_sets(tmp_path):
    source = _write_source(tmp_path)
    plan = build_plan(
        source,
        existing_provider_names={"Anthropic"},
        existing_model_keys={("Anthropic", "claude-sonnet-4-6")},
        existing_agent_names={"intel"},
    )
    assert any(
        p.already_present for p in plan.providers if p.display_name == "Anthropic"
    )
    assert any(
        m.already_present
        for m in plan.models
        if m.model_id == "claude-sonnet-4-6"
    )
    assert any(a.already_present for a in plan.agents if a.agent_name == "intel")


def test_render_plan_mentions_gaps(tmp_path):
    source = _write_source(tmp_path)
    plan = build_plan(source)
    out = render_plan(plan)
    assert "Providers to create: 2" in out
    assert "Workspaces not yet copied" in out
    assert "orchestrator" in out


# ---- apply tests ------------------------------------------------------------


def test_apply_plan_creates_everything(tmp_path):
    source = _write_source(tmp_path)
    plan = build_plan(source)
    cat = FakeCatalog()
    ac = FakeAgentConfig()
    sc = FakeSharedContext()
    result = apply_plan(
        plan,
        catalog_service=cat,
        agent_config_service=ac,
        shared_context_service=sc,
    )
    assert result.providers_created == 2
    assert result.models_created == 4
    # orchestrator routes through upsert (mapped from 'main');
    # intel is a standalone create.
    assert result.agents_created == 1
    assert result.agents_updated == 1
    assert result.context_created == 3
    assert not result.errors


def test_apply_plan_is_idempotent(tmp_path):
    source = _write_source(tmp_path)
    cat = FakeCatalog()
    ac = FakeAgentConfig()
    sc = FakeSharedContext()
    # First run
    plan1 = build_plan(source)
    apply_plan(plan1, catalog_service=cat, agent_config_service=ac, shared_context_service=sc)

    # Snapshot existing sets, build second plan, apply
    provider_names = {p.name for p in cat.providers}
    id_by_name = {p.id: p.name for p in cat.providers}
    model_keys = {
        (id_by_name[m.provider_id], m.model_id) for m in cat.models
    }
    agent_names = {a["name"] for a in ac.list_agents()}

    plan2 = build_plan(
        source,
        existing_provider_names=provider_names,
        existing_model_keys=model_keys,
        existing_agent_names=agent_names,
    )
    # Skip context on second run since there's no dedup layer for entries.
    result2 = apply_plan(
        plan2,
        catalog_service=cat,
        agent_config_service=ac,
        shared_context_service=sc,
        skip_context=True,
    )
    # Nothing new should have been created.
    assert result2.providers_created == 0
    assert result2.models_created == 0
    assert result2.agents_created == 0
    # Updates may or may not fire depending on deltas; just assert no errors.
    assert not result2.errors


def test_apply_plan_writes_orchestrator_via_upsert(tmp_path):
    source = _write_source(tmp_path)
    plan = build_plan(source)
    cat = FakeCatalog()
    ac = FakeAgentConfig()
    # Pretend orchestrator already has a baseline .md in the repo.
    ac.baselines.add("orchestrator")
    sc = FakeSharedContext()
    apply_plan(
        plan,
        catalog_service=cat,
        agent_config_service=ac,
        shared_context_service=sc,
    )
    # orchestrator goes through upsert_override, not create_standalone
    assert not any(
        c["agent_name"] == "orchestrator" for c in ac.create_standalone_calls
    )
    assert any(
        c["agent_name"] == "orchestrator" for c in ac.upsert_calls
    )


def test_apply_plan_picks_up_workspace_on_rerun(tmp_path):
    # First run: no workspace files yet.
    source = _write_source(tmp_path, with_workspace=False)
    cat = FakeCatalog()
    ac = FakeAgentConfig()
    sc = FakeSharedContext()
    plan1 = build_plan(source)
    apply_plan(plan1, catalog_service=cat, agent_config_service=ac, shared_context_service=sc, skip_context=True)
    # intel created with placeholder body
    intel_body = ac.overrides["intel"].get("body_override") or ""
    assert "Imported from OpenClaw" in intel_body or intel_body.startswith("# intel")

    # Now drop the workspace files in place and re-run.
    ws = source / "workspaces" / "workspace-intel"
    ws.mkdir(parents=True)
    (ws / "AGENTS.md").write_text("# Intel real body")
    (ws / "SOUL.md").write_text("# Intel soul")

    provider_names = {p.name for p in cat.providers}
    id_by_name = {p.id: p.name for p in cat.providers}
    model_keys = {
        (id_by_name[m.provider_id], m.model_id) for m in cat.models
    }
    agent_names = {a["name"] for a in ac.list_agents()}
    plan2 = build_plan(
        source,
        existing_provider_names=provider_names,
        existing_model_keys=model_keys,
        existing_agent_names=agent_names,
    )
    apply_plan(plan2, catalog_service=cat, agent_config_service=ac, shared_context_service=sc, skip_context=True)

    # Second run should have upserted body_override with workspace content.
    found = [c for c in ac.upsert_calls if c["agent_name"] == "intel"]
    assert found
    last_patch = found[-1]["patch"]
    assert last_patch.get("body_override") is not None
    assert "Intel real body" in last_patch["body_override"]
    assert last_patch.get("soul_overlay") is not None


def test_apply_plan_context_namespace_values(tmp_path):
    source = _write_source(tmp_path)
    plan = build_plan(source)
    cat = FakeCatalog()
    ac = FakeAgentConfig()
    sc = FakeSharedContext()
    apply_plan(
        plan,
        catalog_service=cat,
        agent_config_service=ac,
        shared_context_service=sc,
        skip_providers=True,
        skip_agents=True,
    )
    namespaces = {w["namespace"] for w in sc.writes}
    assert "feeds" in namespaces
    assert "research:scott" in namespaces
    assert "root" in namespaces
    for w in sc.writes:
        assert w["created_by"] == "openclaw-import"
        assert w["metadata"]["source"] == "openclaw-import"


# ---- cron import tests ------------------------------------------------------


def _sample_cron_at_system_event() -> dict:
    return {
        "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "agentId": "main",
        "name": "Reminder: dentist",
        "enabled": False,
        "createdAtMs": 1769654164017,
        "updatedAtMs": 1769654164036,
        "schedule": {"kind": "at", "at": "2025-02-04T00:00:00.000Z"},
        "sessionTarget": "main",
        "wakeMode": "next-heartbeat",
        "payload": {"kind": "systemEvent", "text": "Don't forget dentist!"},
        "state": {"lastRunAtMs": 1769654164036, "lastStatus": "ok"},
    }


def _sample_cron_cron_agent_turn() -> dict:
    return {
        "id": "11111111-2222-3333-4444-555555555555",
        "agentId": "intel",
        "name": "Feed digest",
        "enabled": True,
        "createdAtMs": 1774200000000,
        "updatedAtMs": 1774200000000,
        "schedule": {
            "kind": "cron",
            "expr": "0 10 * * *",
            "tz": "America/Chicago",
        },
        "sessionTarget": "isolated",
        "wakeMode": "now",
        "payload": {
            "kind": "agentTurn",
            "message": "Pull feeds and write digest",
            "timeoutSeconds": 600,
        },
        "delivery": {
            "mode": "announce",
            "channel": "slack",
            "bestEffort": True,
            "to": "user:U123",
        },
        "state": {
            "lastRunAtMs": 1774271804929,
            "lastStatus": "ok",
            "consecutiveErrors": 0,
        },
    }


def test_load_crons_parses_jobs_file(tmp_path):
    """Fixture with 2 sample CronJob dicts. Returns Cron objects with right types."""
    cron_dir = tmp_path / "cron"
    cron_dir.mkdir()
    jobs = {"version": 1, "jobs": [_sample_cron_at_system_event(), _sample_cron_cron_agent_turn()]}
    (cron_dir / "jobs.json").write_text(json.dumps(jobs))

    raw_list = _load_crons(tmp_path)
    assert len(raw_list) == 2

    c1 = _build_cron_from_dict(raw_list[0])
    assert isinstance(c1, Cron)
    assert isinstance(c1.schedule, AtSchedule)
    assert isinstance(c1.payload, SystemEventPayload)
    assert c1.title == "Reminder: dentist"
    assert c1.enabled is False
    assert c1.wake_mode == "next-heartbeat"

    c2 = _build_cron_from_dict(raw_list[1])
    assert isinstance(c2, Cron)
    assert isinstance(c2.schedule, CronExprSchedule)
    assert c2.schedule.tz == "America/Chicago"
    assert isinstance(c2.payload, AgentTurnPayload)
    assert c2.payload.timeout_seconds == 600
    assert c2.assignee == "intel"


def test_cron_main_agent_id_maps_to_orchestrator():
    raw = _sample_cron_at_system_event()
    assert raw["agentId"] == "main"
    cron = _build_cron_from_dict(raw)
    assert cron.assignee == "orchestrator"


class FakeCronService:
    """Minimal stub for CronService in import tests."""

    def __init__(self):
        self.crons: dict[str, dict] = {}
        self.creates: list[dict] = []
        self.updates: list[dict] = []

    def list_all(self):
        return list(self.crons.values())

    def create(self, title, assignee, **kw):
        cron = Cron(title=title, assignee=assignee, **kw)
        self.crons[cron.id] = cron
        self.creates.append({"title": title})
        return cron

    def update(self, cron_id, **kw):
        self.updates.append({"id": cron_id, **kw})
        return self.crons.get(cron_id)


def test_cron_apply_idempotent(tmp_path):
    """Apply twice; second run should update, not create duplicates."""
    source = tmp_path / "src"
    source.mkdir()
    (source / "openclaw.json").write_text(json.dumps(
        {"agents": {"defaults": {}, "list": []}, "models": {"providers": {}}}
    ))
    cron_dir = source / "cron"
    cron_dir.mkdir()
    jobs = {"version": 1, "jobs": [_sample_cron_cron_agent_turn()]}
    (cron_dir / "jobs.json").write_text(json.dumps(jobs))

    svc = FakeCronService()

    plan1 = build_plan(
        source,
        skip_providers=True,
        skip_agents=True,
        skip_context=True,
    )
    assert len(plan1.crons) == 1
    result1 = apply_plan(
        plan1,
        catalog_service=None,
        agent_config_service=None,
        shared_context_service=None,
        cron_service=svc,
        skip_providers=True,
        skip_agents=True,
        skip_context=True,
    )
    assert result1.crons_created == 1

    # Second apply: mark existing ids
    plan2 = build_plan(
        source,
        skip_providers=True,
        skip_agents=True,
        skip_context=True,
        existing_cron_ids={ce.cron.id for ce in plan1.crons},
    )
    assert plan2.crons[0].already_present is True
    result2 = apply_plan(
        plan2,
        catalog_service=None,
        agent_config_service=None,
        shared_context_service=None,
        cron_service=svc,
        skip_providers=True,
        skip_agents=True,
        skip_context=True,
    )
    assert result2.crons_created == 0
    assert result2.crons_updated == 1


# ---- skill import tests -----------------------------------------------------


def test_discover_skills_finds_skill_md_dirs(tmp_path):
    ws = tmp_path / "workspaces" / "workspace" / "skills"
    s1 = ws / "alpha"
    s1.mkdir(parents=True)
    (s1 / "SKILL.md").write_text("# Alpha")
    (s1 / "helper.py").write_text("pass")

    s2 = ws / "beta"
    s2.mkdir()
    (s2 / "SKILL.md").write_text("# Beta")

    # dir without SKILL.md should NOT be discovered
    s3 = ws / "gamma"
    s3.mkdir()
    (s3 / "README.md").write_text("no skill")

    result = _discover_skills(tmp_path)
    names = [n for n, _ in result]
    assert "alpha" in names
    assert "beta" in names
    assert "gamma" not in names


def test_skill_apply_copies_files_and_ignores_node_modules(tmp_path):
    source = tmp_path / "src"
    ws = source / "workspaces" / "workspace" / "skills" / "test-skill"
    ws.mkdir(parents=True)
    (ws / "SKILL.md").write_text("# Test Skill")
    (ws / "run.py").write_text("print('hi')")
    nm = ws / "node_modules" / "foo"
    nm.mkdir(parents=True)
    (nm / "index.js").write_text("module.exports = {}")
    pycache = ws / "__pycache__"
    pycache.mkdir()
    (pycache / "cached.pyc").write_text("bytes")

    target_root = tmp_path / "skills"
    target_root.mkdir()

    (source / "openclaw.json").write_text(json.dumps(
        {"agents": {"defaults": {}, "list": []}, "models": {"providers": {}}}
    ))

    plan = build_plan(
        source,
        skip_providers=True,
        skip_agents=True,
        skip_context=True,
        skip_crons=True,
        skills_target_dir=target_root,
    )
    assert len(plan.skills) == 1
    assert plan.skills[0].name == "test-skill"

    result = apply_plan(
        plan,
        catalog_service=None,
        agent_config_service=None,
        shared_context_service=None,
        skip_providers=True,
        skip_agents=True,
        skip_context=True,
        skip_crons=True,
    )
    assert result.skills_imported == 1
    target = target_root / "test-skill"
    assert (target / "SKILL.md").is_file()
    assert (target / "run.py").is_file()
    assert not (target / "node_modules").exists()
    assert not (target / "__pycache__").exists()


def test_skill_dedup_prefers_main_workspace(tmp_path):
    """When same skill name exists in multiple workspaces, prefer 'workspace'."""
    ws1 = tmp_path / "workspaces" / "workspace" / "skills" / "shared-skill"
    ws1.mkdir(parents=True)
    (ws1 / "SKILL.md").write_text("# From main workspace")

    ws2 = tmp_path / "workspaces" / "workspace-adlan" / "skills" / "shared-skill"
    ws2.mkdir(parents=True)
    (ws2 / "SKILL.md").write_text("# From adlan workspace")

    result = _discover_skills(tmp_path)
    assert len([n for n, _ in result if n == "shared-skill"]) == 1
    _, path = next((n, p) for n, p in result if n == "shared-skill")
    assert "workspace" in path.parts and "workspace-adlan" not in str(path)
