"use client";

/**
 * Admin page: Heartbeat Health.
 *
 * Shows per-agent health cards plus a live tail of the last 50 heartbeat
 * events. Polls /admin/heartbeat/health and /admin/heartbeat/events every 10s.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { HeartbeatHealthCard } from "@/components/admin/heartbeat-health-card";
import { HeartbeatEventList } from "@/components/admin/heartbeat-event-list";
import { createApiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/auth-context";
import type { AgentHealth, HeartbeatEvent } from "@/types";

const POLL_INTERVAL_MS = 10_000;

function HeartbeatContent() {
  const { getIdToken } = useAuth();
  const [agents, setAgents] = useState<AgentHealth[]>([]);
  const [events, setEvents] = useState<HeartbeatEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const initialLoadRef = useRef(true);

  const fetchData = useCallback(async () => {
    try {
      const api = createApiClient(getIdToken);
      const [healthData, eventsData] = await Promise.all([
        api.getHeartbeatHealth(),
        api.getHeartbeatEvents(50),
      ]);
      setAgents(healthData.agents ?? []);
      setEvents(eventsData ?? []);
      setError(null);
      setLastRefresh(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load heartbeat data");
    } finally {
      if (initialLoadRef.current) {
        initialLoadRef.current = false;
        setLoading(false);
      }
    }
  }, [getIdToken]);

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [fetchData]);

  const hasAnyActivity = events.length > 0 || agents.length > 0;

  return (
    <div className="flex h-screen flex-col bg-slate-900 text-slate-100">
      <header className="flex items-center justify-between border-b border-slate-700 px-6 py-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-100">Heartbeat Health</h1>
            <span
              className={`rounded-md border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${
                hasAnyActivity
                  ? "border-green-700 bg-green-600/20 text-green-400"
                  : "border-slate-600 bg-slate-800 text-slate-400"
              }`}
            >
              {hasAnyActivity ? "ACTIVE" : "IDLE"}
            </span>
          </div>
          <p className="text-sm text-slate-400 mt-0.5">
            Live view of agent wake events and per-agent status.
            {lastRefresh && (
              <>
                {" · "}
                <span className="text-slate-500">
                  updated {lastRefresh.toLocaleTimeString()}
                </span>
              </>
            )}
          </p>
        </div>
        <button
          onClick={fetchData}
          disabled={loading}
          className="flex items-center gap-2 rounded-md border border-slate-600 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-800 disabled:opacity-50 transition-colors"
        >
          <svg
            className={`h-4 w-4 ${loading ? "animate-spin" : ""}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
          Refresh
        </button>
      </header>

      <main className="flex-1 overflow-y-auto p-6 space-y-6">
        {error && (
          <div className="rounded-md border border-red-700 bg-red-900/30 px-4 py-3 text-sm text-red-400">
            {error}
          </div>
        )}

        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
            Agents
          </h2>
          {loading && agents.length === 0 ? (
            <div className="flex items-center justify-center py-16">
              <div className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-400 border-t-transparent" />
            </div>
          ) : agents.length === 0 ? (
            <div className="rounded-md border border-slate-700 bg-slate-900 px-4 py-8 text-center text-sm text-slate-500">
              No agent heartbeats observed yet.
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {agents.map((a) => (
                <HeartbeatHealthCard
                  key={a.agent_id}
                  health={a}
                  onTrigger={(id) => {
                    const api = createApiClient(getIdToken);
                    return api
                      .triggerHeartbeat(id)
                      .then(() => fetchData())
                      .catch((err) => {
                        setError(
                          err instanceof Error
                            ? err.message
                            : "Failed to trigger heartbeat",
                        );
                      });
                  }}
                />
              ))}
            </div>
          )}
        </section>

        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
            Recent events
          </h2>
          <HeartbeatEventList events={events} />
        </section>
      </main>
    </div>
  );
}

export default function HeartbeatAdminPage() {
  return (
    <AppShell>
      <HeartbeatContent />
    </AppShell>
  );
}
