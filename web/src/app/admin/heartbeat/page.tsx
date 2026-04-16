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
    <div className="flex h-full flex-col bg-ink-900 text-paper">
      <header className="hairline-b px-8 pt-6 pb-5 flex items-end justify-between gap-4">
        <div>
          <div className="label-caps mb-1.5">§ 09 · VITALS</div>
          <div className="flex items-baseline gap-3">
            <h1 className="font-display text-[30px] italic leading-none">
              Heartbeat Health
            </h1>
            <span
              className={`font-mono text-[10px] uppercase tracking-[0.16em] flex items-center gap-1.5 ${
                hasAnyActivity ? "text-signal" : "text-paper-40"
              }`}
            >
              {hasAnyActivity && <span className="phosphor-dot" />}
              {hasAnyActivity ? "ACTIVE" : "IDLE"}
            </span>
          </div>
          <p className="mt-2 font-body text-[13px] text-paper-60">
            Live view of agent wake events and per-agent status.
            {lastRefresh && (
              <>
                {" · "}
                <span className="font-mono text-[11px] uppercase tracking-widest text-paper-40">
                  UPDATED {lastRefresh.toLocaleTimeString()}
                </span>
              </>
            )}
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
