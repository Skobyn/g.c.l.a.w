"use client";

import { useState, useEffect, useCallback } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { CronTable } from "@/components/crons/cron-table";
import { CreateCronForm } from "@/components/crons/create-cron-form";
import { createApiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/auth-context";
import type { CronInfo } from "@/types";

function CronsContent() {
  const { getIdToken } = useAuth();
  const [crons, setCrons] = useState<CronInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const [triggeringId, setTriggeringId] = useState<string | null>(null);

  const fetchCrons = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const api = createApiClient(getIdToken);
      const data = await api.getCrons();
      setCrons(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load crons");
    } finally {
      setLoading(false);
    }
  }, [getIdToken]);

  useEffect(() => {
    fetchCrons();
  }, [fetchCrons]);

  const handleToggle = async (cronId: string) => {
    setTogglingId(cronId);
    try {
      const api = createApiClient(getIdToken);
      const updated = await api.toggleCron(cronId);
      setCrons((prev) => prev.map((c) => (c.id === cronId ? updated : c)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to toggle cron");
    } finally {
      setTogglingId(null);
    }
  };

  const handleTrigger = async (cronId: string) => {
    setTriggeringId(cronId);
    try {
      const api = createApiClient(getIdToken);
      await api.triggerCron(cronId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to trigger cron");
    } finally {
      setTriggeringId(null);
    }
  };

  const handleCreated = (cron: CronInfo) => {
    setCrons((prev) => [cron, ...prev]);
    setShowCreateForm(false);
  };

  return (
    <div className="flex h-full flex-col bg-ink-900 text-paper">
      <header className="hairline-b px-8 pt-6 pb-5">
        <div className="flex items-end justify-between">
          <div>
            <div className="label-caps mb-1.5">§ 03 · SCHEDULE</div>
            <h1 className="font-display text-[30px] italic leading-none">Crons</h1>
            <p className="mt-2 font-body text-[13px] text-paper-60">
              {crons.length} job{crons.length !== 1 ? "s" : ""} on the wire
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={fetchCrons}
              disabled={loading}
              className="btn-hair"
            >
              {loading ? "REFRESHING…" : "REFRESH"}
            </button>
            <button
              onClick={() => setShowCreateForm((prev) => !prev)}
              className="btn-hair-signal"
            >
              + New Cron
            </button>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="flex-1 overflow-y-auto p-6 space-y-6">
        {error && (
          <div className="rounded-md border border-red-700 bg-red-900/30 px-4 py-3 text-sm text-red-400">
            {error}
          </div>
        )}

        {/* Create form panel */}
        {showCreateForm && (
          <div className="rounded-lg border border-slate-700 bg-slate-800 p-5">
            <h2 className="text-base font-semibold text-slate-100 mb-4">Create New Cron Job</h2>
            <CreateCronForm
              onCreated={handleCreated}
              onCancel={() => setShowCreateForm(false)}
            />
          </div>
        )}

        {loading && crons.length === 0 ? (
          <div className="flex items-center justify-center py-16">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-400 border-t-transparent" />
          </div>
        ) : (
          <CronTable
            crons={crons}
            onToggle={handleToggle}
            onTrigger={handleTrigger}
            togglingId={togglingId}
            triggeringId={triggeringId}
          />
        )}
      </main>
    </div>
  );
}

export default function CronsPage() {
  return (
    <AppShell>
      <CronsContent />
    </AppShell>
  );
}
