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
    <div className="flex h-screen flex-col bg-slate-900 text-slate-100">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-slate-700 px-6 py-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Crons</h1>
          <p className="text-sm text-slate-400 mt-0.5">
            {crons.length} cron job{crons.length !== 1 ? "s" : ""} configured
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={fetchCrons}
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
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Refresh
          </button>
          <button
            onClick={() => setShowCreateForm((prev) => !prev)}
            className="flex items-center gap-2 rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 transition-colors"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
            </svg>
            New Cron
          </button>
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
