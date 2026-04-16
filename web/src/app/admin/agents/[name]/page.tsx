"use client";

/**
 * /admin/agents/[name] — Agent detail / edit.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { AppShell } from "@/components/layout/app-shell";
import { createApiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/auth-context";
import type {
  AgentListEntry,
  AgentOverride,
  CatalogModel,
  EffectiveAgentConfig,
  SkillInfo,
} from "@/types";
import { AgentTabsNav, type TabId } from "@/components/admin/agents/agent-tabs-nav";
import { TabOverview } from "@/components/admin/agents/tab-overview";
import { TabIdentity } from "@/components/admin/agents/tab-identity";
import { TabModel } from "@/components/admin/agents/tab-model";
import { TabTools } from "@/components/admin/agents/tab-tools";
import { TabSkills } from "@/components/admin/agents/tab-skills";
import { TabSubagents } from "@/components/admin/agents/tab-subagents";
import { TabHeartbeat } from "@/components/admin/agents/tab-heartbeat";
import { TabInstructions } from "@/components/admin/agents/tab-instructions";
import { TabSoul } from "@/components/admin/agents/tab-soul";
import { Banner } from "@/components/admin/agents/shared";

function AgentDetailContent({ name }: { name: string }) {
  const { getIdToken } = useAuth();
  const api = useMemo(() => createApiClient(getIdToken), [getIdToken]);
  const router = useRouter();

  const [config, setConfig] = useState<EffectiveAgentConfig | null>(null);
  const [override, setOverride] = useState<AgentOverride | null>(null);
  const [baseline, setBaseline] = useState<string>("");
  const [baselineError, setBaselineError] = useState<string | null>(null);
  const [models, setModels] = useState<CatalogModel[]>([]);
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [skillsError, setSkillsError] = useState<string | null>(null);
  const [allAgents, setAllAgents] = useState<AgentListEntry[]>([]);

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const [dirtyTabs, setDirtyTabs] = useState<Set<TabId>>(new Set());

  const setTabDirty = useCallback((tab: TabId, dirty: boolean) => {
    setDirtyTabs((prev) => {
      const next = new Set(prev);
      if (dirty) next.add(tab);
      else next.delete(tab);
      return next;
    });
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [cfg, ov, agents] = await Promise.all([
        api.getAgentConfig(name),
        api.getAgentOverride(name),
        api.listAgentsRich().catch(() => []),
      ]);
      setConfig(cfg);
      setOverride(ov);
      setAllAgents(agents);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Failed to load agent");
    } finally {
      setLoading(false);
    }

    // Parallel best-effort loads
    api
      .getAgentBaseline(name)
      .then((b) => {
        setBaseline(b.body);
        setBaselineError(null);
      })
      .catch((err) => {
        setBaseline("");
        setBaselineError(err instanceof Error ? err.message : String(err));
      });

    api
      .listModels()
      .then(setModels)
      .catch(() => setModels([]));

    api
      .getSkills()
      .then((s) => {
        setSkills(s);
        setSkillsError(null);
      })
      .catch((err) => {
        setSkills([]);
        setSkillsError(err instanceof Error ? err.message : String(err));
      });
  }, [api, name]);

  useEffect(() => {
    load();
  }, [load]);

  async function applyPatch(patch: Partial<AgentOverride>) {
    setActionError(null);
    try {
      const updated = await api.updateAgent(name, patch);
      setOverride(updated);
      // Refresh the effective config too
      const cfg = await api.getAgentConfig(name);
      setConfig(cfg);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Update failed";
      setActionError(msg);
      throw err;
    }
  }

  async function handleToggleEnabled(v: boolean) {
    await applyPatch({ enabled: v });
  }

  async function handleRevert() {
    setActionError(null);
    try {
      await api.deleteAgent(name, false);
      await load();
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Failed to revert",
      );
    }
  }

  async function handleDelete() {
    setActionError(null);
    try {
      const res = await api.deleteAgent(name, true);
      if (res.deleted) {
        router.push("/admin/agents");
      } else {
        await load();
      }
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Failed to delete",
      );
    }
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center bg-ink-900 text-paper">
        <p className="font-mono text-[11px] uppercase tracking-widest text-paper-40">
          LOADING AGENT<span className="signal-cursor" />
        </p>
      </div>
    );
  }

  if (loadError || !config) {
    return (
      <div className="flex h-full flex-col bg-ink-900 text-paper">
        <header className="hairline-b px-8 pt-6 pb-5">
          <Link
            href="/admin/agents"
            className="font-mono text-[10px] uppercase tracking-widest text-paper-40 hover:text-signal"
          >
            ← BACK TO REGISTER
          </Link>
          <h1 className="mt-2 font-display text-[28px] italic">{name}</h1>
        </header>
        <main className="flex-1 p-8">
          <Banner tone="red">{loadError || "Agent not found"}</Banner>
        </main>
      </div>
    );
  }

  // Effective values for each tab — prefer override, fall back to baseline
  const identity = override?.identity ?? config.identity;
  const model = override?.model ?? config.model;
  const tools = override?.tools ?? config.tools;
  const subagents = override?.subagents ?? config.subagents;
  const heartbeat =
    override?.heartbeat !== undefined ? override.heartbeat : config.heartbeat;
  const skillsVal =
    override?.skills !== undefined ? override.skills : config.skills;
  const soulVal =
    override?.soul_overlay !== undefined
      ? override.soul_overlay
      : config.soul_overlay;
  const enabled = override?.enabled ?? true;

  return (
    <div className="flex h-full flex-col bg-ink-900 text-paper">
      <header className="hairline-b px-8 pt-6 pb-5">
        <Link
          href="/admin/agents"
          className="font-mono text-[10px] uppercase tracking-widest text-paper-40 hover:text-signal transition-colors"
        >
          ← BACK TO REGISTER
        </Link>
        <div className="mt-2 flex items-baseline gap-3">
          {identity.emoji && (
            <span className="text-xl">{identity.emoji}</span>
          )}
          <h1 className="font-display text-[30px] italic leading-none">
            {identity.display_name || config.name}
          </h1>
          <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-paper-40">
            {config.name}
          </span>
          {!enabled && (
            <span className="label-caps" style={{ color: "var(--alert)" }}>
              · DISABLED
            </span>
          )}
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <aside className="w-[220px] shrink-0 overflow-y-auto hairline-r bg-ink-900">
          <AgentTabsNav
            active={activeTab}
            onChange={setActiveTab}
            dirtyTabs={dirtyTabs}
          />
        </aside>

        <main className="flex-1 overflow-y-auto px-8 py-6">
          {actionError && (
            <div className="mb-4">
              <Banner tone="red">{actionError}</Banner>
            </div>
          )}

          {activeTab === "overview" && (
            <TabOverview
              config={config}
              enabled={enabled}
              onToggleEnabled={handleToggleEnabled}
              onRevert={handleRevert}
              onDelete={handleDelete}
              overrideTimestamps={
                override
                  ? {
                      created_at: override.created_at,
                      updated_at: override.updated_at,
                    }
                  : null
              }
            />
          )}

          {activeTab === "identity" && (
            <TabIdentity
              value={identity}
              onSave={applyPatch}
              onDirtyChange={(d) => setTabDirty("identity", d)}
            />
          )}

          {activeTab === "model" && (
            <TabModel
              value={model}
              models={models}
              onSave={applyPatch}
              onDirtyChange={(d) => setTabDirty("model", d)}
            />
          )}

          {activeTab === "tools" && (
            <TabTools
              value={tools}
              onSave={applyPatch}
              onDirtyChange={(d) => setTabDirty("tools", d)}
            />
          )}

          {activeTab === "skills" && (
            <TabSkills
              value={skillsVal}
              skills={skills}
              skillsError={skillsError}
              onSave={applyPatch}
              onDirtyChange={(d) => setTabDirty("skills", d)}
            />
          )}

          {activeTab === "subagents" && (
            <TabSubagents
              value={subagents}
              allAgents={allAgents}
              selfName={config.name}
              onSave={applyPatch}
              onDirtyChange={(d) => setTabDirty("subagents", d)}
            />
          )}

          {activeTab === "heartbeat" && (
            <TabHeartbeat
              value={heartbeat}
              onSave={applyPatch}
              onDirtyChange={(d) => setTabDirty("heartbeat", d)}
            />
          )}

          {activeTab === "instructions" && (
            <TabInstructions
              bodyOverride={override?.body_override ?? null}
              systemPromptOverride={override?.system_prompt_override ?? null}
              baseline={baseline}
              baselineError={baselineError}
              onSave={applyPatch}
              onDirtyChange={(d) => setTabDirty("instructions", d)}
            />
          )}

          {activeTab === "soul" && (
            <TabSoul
              value={soulVal}
              onSave={applyPatch}
              onDirtyChange={(d) => setTabDirty("soul", d)}
            />
          )}
        </main>
      </div>
    </div>
  );
}

export default function AgentDetailPage() {
  const params = useParams<{ name: string }>();
  const name = decodeURIComponent(params.name);
  return (
    <AppShell>
      <AgentDetailContent name={name} />
    </AppShell>
  );
}
