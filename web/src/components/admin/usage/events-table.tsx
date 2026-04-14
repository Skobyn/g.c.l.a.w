"use client";

/**
 * Recent events table with kind filter chips and Load more.
 *
 * Parent owns data + limit state; this component renders the rows and emits
 * kind / load-more intents upward.
 */

import type { UsageEvent, UsageKind } from "@/types";
import { KindBadge } from "./kind-badge";

interface EventsTableProps {
  events: UsageEvent[];
  kindFilter: UsageKind | "all";
  onKindFilterChange: (kind: UsageKind | "all") => void;
  onLoadMore: () => void;
  loading?: boolean;
  hasMore?: boolean;
  collapsed: boolean;
  onToggleCollapsed: () => void;
}

const KINDS: Array<UsageKind | "all"> = ["all", "model", "agent", "skill", "tool"];

function formatTime(ts: string): string {
  try {
    return new Date(ts).toLocaleTimeString();
  } catch {
    return ts;
  }
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

export function EventsTable({
  events,
  kindFilter,
  onKindFilterChange,
  onLoadMore,
  loading,
  hasMore,
  collapsed,
  onToggleCollapsed,
}: EventsTableProps) {
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/60">
      <button
        onClick={onToggleCollapsed}
        className="flex w-full items-center justify-between border-b border-slate-700 px-4 py-2 text-left text-sm font-semibold text-slate-200 hover:bg-slate-800/40"
      >
        <span>Recent Events {events.length > 0 && <span className="ml-1 text-slate-500 font-normal">({events.length})</span>}</span>
        <svg
          className={`h-4 w-4 transition-transform ${collapsed ? "" : "rotate-180"}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {!collapsed && (
        <>
          <div className="flex flex-wrap items-center gap-1.5 border-b border-slate-700 px-4 py-2">
            {KINDS.map((k) => {
              const active = kindFilter === k;
              return (
                <button
                  key={k}
                  onClick={() => onKindFilterChange(k)}
                  className={`rounded-md border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide transition-colors ${
                    active
                      ? "border-indigo-500 bg-indigo-600/30 text-indigo-300"
                      : "border-slate-700 bg-slate-900 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
                  }`}
                >
                  {k}
                </button>
              );
            })}
          </div>

          {events.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-slate-500">
              {loading ? "Loading events…" : "No events in this window yet."}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-wide text-slate-500">
                    <th className="px-4 py-2 font-medium">Time</th>
                    <th className="px-4 py-2 font-medium">Kind</th>
                    <th className="px-4 py-2 font-medium">Name</th>
                    <th className="px-4 py-2 font-medium">Caller</th>
                    <th className="px-4 py-2 text-right font-medium">Duration</th>
                    <th className="px-4 py-2 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((e) => (
                    <tr
                      key={e.id}
                      className="border-t border-slate-800 text-slate-300 hover:bg-slate-800/40"
                    >
                      <td className="px-4 py-2 text-slate-500 tabular-nums">
                        {formatTime(e.timestamp)}
                      </td>
                      <td className="px-4 py-2">
                        <KindBadge kind={e.kind} />
                      </td>
                      <td className="px-4 py-2 font-medium text-slate-200">
                        {e.name}
                      </td>
                      <td className="px-4 py-2 text-slate-400">
                        {e.caller ?? "—"}
                      </td>
                      <td className="px-4 py-2 text-right tabular-nums text-slate-400">
                        {formatDuration(e.duration_ms)}
                      </td>
                      <td className="px-4 py-2">
                        {e.success ? (
                          <span className="rounded-md border border-green-700 bg-green-600/20 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-green-400">
                            ok
                          </span>
                        ) : (
                          <span
                            className="rounded-md border border-red-700 bg-red-600/20 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-red-400"
                            title={e.error ?? undefined}
                          >
                            fail
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="flex justify-center border-t border-slate-700 px-4 py-3">
            <button
              onClick={onLoadMore}
              disabled={loading || !hasMore}
              className="rounded-md border border-slate-600 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {loading
                ? "Loading…"
                : hasMore
                  ? "Load more"
                  : "No more events"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
