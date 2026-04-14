"use client";

/**
 * Admin page: Usage & Cost observability.
 *
 * Consumes /admin/usage/summary and /admin/usage/events to render KPIs,
 * an hourly stacked bar chart, Top-N tables, and a recent events tail.
 * Auto-refreshes every 30s while the tab is visible.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { useApiClient } from "@/lib/api-client";
import type { UsageEvent, UsageKind, UsageSummary } from "@/types";
import { KpiCard } from "@/components/admin/usage/kpi-card";
import { HourlyChart } from "@/components/admin/usage/hourly-chart";
import { TopNTable } from "@/components/admin/usage/top-n-table";
import type { TopNColumn } from "@/components/admin/usage/top-n-table";
import { EventsTable } from "@/components/admin/usage/events-table";

const AUTO_REFRESH_MS = 30_000;
const EVENTS_PAGE_SIZE = 50;

type WindowKey = "1h" | "24h" | "7d" | "30d";

const WINDOW_OPTIONS: Array<{ key: WindowKey; label: string; ms: number }> = [
  { key: "1h", label: "Last hour", ms: 60 * 60 * 1000 },
  { key: "24h", label: "Last 24 hours", ms: 24 * 60 * 60 * 1000 },
  { key: "7d", label: "Last 7 days", ms: 7 * 24 * 60 * 60 * 1000 },
  { key: "30d", label: "Last 30 days", ms: 30 * 24 * 60 * 60 * 1000 },
];

function windowMs(key: WindowKey): number {
  return WINDOW_OPTIONS.find((w) => w.key === key)?.ms ?? 24 * 60 * 60 * 1000;
}

function formatUsd(v: number): string {
  if (v >= 1000) return `$${v.toFixed(0)}`;
  if (v >= 1) return `$${v.toFixed(2)}`;
  return `$${v.toFixed(4)}`;
}

function formatCount(n: number): string {
  return n.toLocaleString();
}

function formatPct(p: number): string {
  return `${(p * 100).toFixed(1)}%`;
}

function UsageContent() {
  const api = useApiClient();
  const [windowKey, setWindowKey] = useState<WindowKey>("24h");
  const [summary, setSummary] = useState<UsageSummary | null>(null);
  const [events, setEvents] = useState<UsageEvent[]>([]);
  const [eventsLimit, setEventsLimit] = useState(EVENTS_PAGE_SIZE);
  const [kindFilter, setKindFilter] = useState<UsageKind | "all">("all");
  const [eventsCollapsed, setEventsCollapsed] = useState(false);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [eventsLoading, setEventsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const initialLoad = useRef(true);

  const since = useMemo(
    () => new Date(Date.now() - windowMs(windowKey)).toISOString(),
    [windowKey],
  );

  const fetchSummary = useCallback(async () => {
    try {
      const data = await api.getUsageSummary({ since, topN: 20 });
      setSummary(data);
      setError(null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load usage summary",
      );
    } finally {
      setSummaryLoading(false);
    }
  }, [api, since]);

  const fetchEvents = useCallback(async () => {
    try {
      const data = await api.getUsageEvents({
        kind: kindFilter === "all" ? undefined : kindFilter,
        limit: eventsLimit,
        since,
      });
      setEvents(data);
      setError(null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load usage events",
      );
    } finally {
      setEventsLoading(false);
    }
  }, [api, kindFilter, eventsLimit, since]);

  const refreshAll = useCallback(async () => {
    await Promise.all([fetchSummary(), fetchEvents()]);
    setLastRefresh(new Date());
    initialLoad.current = false;
  }, [fetchSummary, fetchEvents]);

  // Initial + window-change fetch.
  useEffect(() => {
    setSummaryLoading(true);
    setEventsLoading(true);
    refreshAll();
  }, [refreshAll]);

  // Auto-refresh every 30s while tab is visible.
  useEffect(() => {
    let id: ReturnType<typeof setInterval> | null = null;
    const start = () => {
      if (id !== null) return;
      id = setInterval(() => {
        if (document.visibilityState === "visible") {
          refreshAll();
        }
      }, AUTO_REFRESH_MS);
    };
    const stop = () => {
      if (id !== null) {
        clearInterval(id);
        id = null;
      }
    };
    const onVis = () => {
      if (document.visibilityState === "visible") {
        refreshAll();
        start();
      } else {
        stop();
      }
    };
    if (document.visibilityState === "visible") start();
    document.addEventListener("visibilitychange", onVis);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [refreshAll]);

  const totals = summary?.totals;
  const top = summary?.top;
  const timeseries = summary?.timeseries ?? [];

  const totalCost = totals?.total_cost_usd ?? 0;
  const costTint =
    totalCost > 1 ? "text-amber-400" : "text-slate-100";

  const modelColumns: TopNColumn<NonNullable<UsageSummary["top"]>["models"][number]>[] = [
    { header: "Model", cell: (r) => <span className="font-medium text-slate-200">{r.name}</span> },
    { header: "Calls", align: "right", cell: (r) => formatCount(r.count) },
    { header: "Tokens in", align: "right", cell: (r) => formatCount(r.tokens_in) },
    { header: "Tokens out", align: "right", cell: (r) => formatCount(r.tokens_out) },
    {
      header: "Cost",
      align: "right",
      cell: (r) => (
        <span className={r.cost_usd > 1 ? "text-amber-400" : ""}>
          {formatUsd(r.cost_usd)}
        </span>
      ),
    },
  ];

  const agentColumns: TopNColumn<NonNullable<UsageSummary["top"]>["agents"][number]>[] = [
    { header: "Agent", cell: (r) => <span className="font-medium text-slate-200">{r.name}</span> },
    { header: "Calls", align: "right", cell: (r) => formatCount(r.count) },
    {
      header: "Avg dur",
      align: "right",
      cell: (r) =>
        r.avg_duration_ms < 1000
          ? `${Math.round(r.avg_duration_ms)}ms`
          : `${(r.avg_duration_ms / 1000).toFixed(2)}s`,
    },
    {
      header: "Failure",
      align: "right",
      cell: (r) => (
        <span className={r.failure_rate > 0.05 ? "text-red-400" : ""}>
          {formatPct(r.failure_rate)}
        </span>
      ),
    },
  ];

  const skillColumns: TopNColumn<NonNullable<UsageSummary["top"]>["skills"][number]>[] = [
    { header: "Skill", cell: (r) => <span className="font-medium text-slate-200">{r.name}</span> },
    { header: "Calls", align: "right", cell: (r) => formatCount(r.count) },
  ];

  const toolColumns: TopNColumn<NonNullable<UsageSummary["top"]>["tools"][number]>[] = [
    { header: "Tool", cell: (r) => <span className="font-medium text-slate-200">{r.name}</span> },
    { header: "Calls", align: "right", cell: (r) => formatCount(r.count) },
    {
      header: "Failure",
      align: "right",
      cell: (r) => (
        <span className={r.failure_rate > 0.05 ? "text-red-400" : ""}>
          {formatPct(r.failure_rate)}
        </span>
      ),
    },
  ];

  const hasMoreEvents = events.length >= eventsLimit;

  return (
    <div className="flex h-screen flex-col bg-slate-900 text-slate-100">
      <header className="flex items-center justify-between border-b border-slate-700 px-6 py-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Usage &amp; Cost</h1>
          <p className="mt-0.5 text-sm text-slate-400">
            Model, agent, skill, and tool telemetry across the GClaw platform.
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
        <div className="flex items-center gap-2">
          <label className="text-xs uppercase tracking-wide text-slate-500">
            Window
          </label>
          <select
            value={windowKey}
            onChange={(e) => setWindowKey(e.target.value as WindowKey)}
            className="rounded-md border border-slate-600 bg-slate-800 px-2 py-1.5 text-sm text-slate-200 focus:border-indigo-500 focus:outline-none"
          >
            {WINDOW_OPTIONS.map((w) => (
              <option key={w.key} value={w.key}>
                {w.label}
              </option>
            ))}
          </select>
          <button
            onClick={() => refreshAll()}
            disabled={summaryLoading || eventsLoading}
            className="flex items-center gap-2 rounded-md border border-slate-600 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-800 disabled:opacity-50 transition-colors"
          >
            <svg
              className={`h-4 w-4 ${
                summaryLoading || eventsLoading ? "animate-spin" : ""
              }`}
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
        </div>
      </header>

      <main className="flex-1 overflow-y-auto p-6 space-y-6">
        {error && (
          <div className="rounded-md border border-red-700 bg-red-900/30 px-4 py-3 text-sm text-red-400">
            {error}
          </div>
        )}

        {/* KPI row. */}
        <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <KpiCard
            title="Total cost"
            value={formatUsd(totalCost)}
            valueClassName={costTint}
            subtitle={
              totalCost > 1 ? "High spend in window" : "USD in selected window"
            }
            loading={summaryLoading && !summary}
          />
          <KpiCard
            title="Model calls"
            value={formatCount(totals?.model ?? 0)}
            subtitle="LLM invocations"
            loading={summaryLoading && !summary}
          />
          <KpiCard
            title="Agent invocations"
            value={formatCount(totals?.agent ?? 0)}
            subtitle="Turns across hierarchy"
            loading={summaryLoading && !summary}
          />
          <KpiCard
            title="Tool calls"
            value={formatCount(totals?.tool ?? 0)}
            subtitle={`${formatCount(totals?.skill ?? 0)} skill runs`}
            loading={summaryLoading && !summary}
          />
        </section>

        {/* Hourly chart. */}
        <section>
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-400">
            Activity over time
          </h2>
          {summaryLoading && !summary ? (
            <div className="h-[220px] animate-pulse rounded-lg border border-slate-700 bg-slate-900/60" />
          ) : (
            <HourlyChart timeseries={timeseries} />
          )}
        </section>

        {/* Top-N tables. */}
        <section className="grid gap-4 lg:grid-cols-2">
          <TopNTable
            title="Top models"
            rows={top?.models ?? []}
            columns={modelColumns}
            loading={summaryLoading && !summary}
          />
          <TopNTable
            title="Top agents"
            rows={top?.agents ?? []}
            columns={agentColumns}
            loading={summaryLoading && !summary}
          />
          <TopNTable
            title="Top skills"
            rows={top?.skills ?? []}
            columns={skillColumns}
            loading={summaryLoading && !summary}
          />
          <TopNTable
            title="Top tools"
            rows={top?.tools ?? []}
            columns={toolColumns}
            loading={summaryLoading && !summary}
          />
        </section>

        {/* Recent events. */}
        <section>
          <EventsTable
            events={events}
            kindFilter={kindFilter}
            onKindFilterChange={(k) => {
              setKindFilter(k);
              setEventsLimit(EVENTS_PAGE_SIZE);
            }}
            onLoadMore={() => setEventsLimit((n) => n + EVENTS_PAGE_SIZE)}
            loading={eventsLoading}
            hasMore={hasMoreEvents}
            collapsed={eventsCollapsed}
            onToggleCollapsed={() => setEventsCollapsed((c) => !c)}
          />
        </section>
      </main>
    </div>
  );
}

export default function UsageAdminPage() {
  return (
    <AppShell>
      <UsageContent />
    </AppShell>
  );
}
