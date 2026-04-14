"use client";

/**
 * /admin/agents — Agent management list.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/layout/app-shell";
import { createApiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/auth-context";
import type { AgentListEntry, CreateAgentPayload } from "@/types";
import { AgentListCard } from "@/components/admin/agents/agent-list-card";
import { CreateAgentModal } from "@/components/admin/agents/create-agent-modal";
import { Banner } from "@/components/admin/agents/shared";

function AgentsContent() {
  const { getIdToken } = useAuth();
  const router = useRouter();
  const api = useMemo(() => createApiClient(getIdToken), [getIdToken]);

  const [entries, setEntries] = useState<AgentListEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const list = await api.listAgentsRich();
      setEntries(list);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load agents");
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleCreate(body: CreateAgentPayload) {
    await api.createAgent(body);
    setShowCreate(false);
    await load();
    router.push(`/admin/agents/${encodeURIComponent(body.agent_name)}`);
  }

  return (
    <div className="flex h-screen flex-col bg-slate-900 text-slate-100">
      <header className="flex items-center justify-between border-b border-slate-700 px-6 py-4">
        <div>
          <h1 className="text-2xl font-bold">Agents</h1>
          <p className="mt-0.5 text-sm text-slate-400">
            Manage baseline agents, overrides, and user-created agents.
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
        >
          + Create Agent
        </button>
      </header>

      <main className="flex-1 overflow-y-auto p-6">
        {error && (
          <div className="mb-4">
            <Banner tone="red">{error}</Banner>
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-16">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-400 border-t-transparent" />
          </div>
        ) : entries.length === 0 ? (
          <div className="rounded-md border border-slate-700 bg-slate-900 px-4 py-12 text-center text-sm text-slate-500">
            No agents yet. Click &quot;+ Create Agent&quot; to add one.
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {entries.map((e) => (
              <AgentListCard key={e.name} entry={e} />
            ))}
          </div>
        )}
      </main>

      {showCreate && (
        <CreateAgentModal
          onCreate={handleCreate}
          onClose={() => setShowCreate(false)}
        />
      )}
    </div>
  );
}

export default function AgentsAdminPage() {
  return (
    <AppShell>
      <AgentsContent />
    </AppShell>
  );
}
