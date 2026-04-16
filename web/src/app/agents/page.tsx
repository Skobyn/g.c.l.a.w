"use client";

import { useState, useEffect, useCallback } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { AgentCard } from "@/components/agents/agent-card";
import { createApiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/auth-context";
import type { AgentInfo, HeartbeatLogEntry } from "@/types";

function AgentDashboardContent() {
  const { getIdToken } = useAuth();
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [heartbeatLogs, setHeartbeatLogs] = useState<HeartbeatLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const api = createApiClient(getIdToken);
      const [agentsData, logsData] = await Promise.all([
        api.getAgents(),
        api.getHeartbeatLogs(20),
      ]);
      setAgents(agentsData);
      setHeartbeatLogs(logsData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load agent data");
    } finally {
      setLoading(false);
    }
  }, [getIdToken]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return (
    <div className="flex h-full flex-col bg-ink-900 text-paper">
      <header className="hairline-b px-8 pt-6 pb-5 flex items-end justify-between">
        <div>
          <div className="label-caps mb-1.5">§ DASHBOARD</div>
          <h1 className="font-display text-[30px] italic leading-none">
            Agent Dashboard
          </h1>
          <p className="mt-2 font-body text-[13px] text-paper-60">
            Monitor and configure your agents.
          </p>
        </div>
        <button
          onClick={fetchData}
          disabled={loading}
          className="btn-hair"
        >
          {loading ? "REFRESHING…" : "REFRESH"}
        </button>
      </header>

      {/* Content */}
      <main className="flex-1 overflow-y-auto p-6">
        {error && (
          <div className="mb-4 rounded-md border border-red-700 bg-red-900/30 px-4 py-3 text-sm text-red-400">
            {error}
          </div>
        )}

        {loading && agents.length === 0 ? (
          <div className="flex items-center justify-center py-16">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-400 border-t-transparent" />
          </div>
        ) : agents.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-slate-500">
            <svg className="h-12 w-12 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
            <p className="text-sm">No agents found</p>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-1 lg:grid-cols-2">
            {agents.map((agent) => (
              <AgentCard
                key={agent.name}
                agent={agent}
                heartbeatLogs={heartbeatLogs}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

export default function AgentsPage() {
  return (
    <AppShell>
      <AgentDashboardContent />
    </AppShell>
  );
}
