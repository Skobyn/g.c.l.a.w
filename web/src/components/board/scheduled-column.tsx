"use client";

/**
 * ScheduledColumn — the leftmost column of the unified board, rendering
 * cron jobs sorted by next_run ascending. Active crons render first;
 * paused crons drop to the bottom, visually muted.
 */

import type { CronInfo } from "@/types";
import { CronCard } from "./cron-card";

interface ScheduledColumnProps {
  crons: CronInfo[];
  loading: boolean;
  error: string | null;
  onCronClick: (cron: CronInfo) => void;
}

function sortCrons(crons: CronInfo[]): CronInfo[] {
  // Active first (sorted by next_run asc, nulls last), then paused.
  const active: CronInfo[] = [];
  const paused: CronInfo[] = [];
  for (const c of crons) {
    if (c.status === "paused" || !c.enabled) paused.push(c);
    else active.push(c);
  }
  const byNext = (a: CronInfo, b: CronInfo) => {
    const ta = a.next_run ? new Date(a.next_run).getTime() : Infinity;
    const tb = b.next_run ? new Date(b.next_run).getTime() : Infinity;
    return ta - tb;
  };
  active.sort(byNext);
  paused.sort(byNext);
  return [...active, ...paused];
}

export function ScheduledColumn({
  crons,
  loading,
  error,
  onCronClick,
}: ScheduledColumnProps) {
  const sorted = sortCrons(crons);

  return (
    <div className="flex w-64 shrink-0 flex-col rounded-xl border border-slate-700 bg-slate-900">
      <div className="sticky top-0 z-10 flex items-center justify-between rounded-t-xl border-b-2 border-purple-500 bg-slate-800 px-3 py-2">
        <span className="text-sm font-semibold text-slate-200">Scheduled</span>
        <span className="rounded-full bg-slate-700 px-2 py-0.5 text-xs font-medium text-slate-300">
          {crons.length}
        </span>
      </div>

      <div className="flex flex-1 flex-col gap-2 overflow-y-auto p-2">
        {loading && crons.length === 0 ? (
          <p className="py-4 text-center text-xs text-slate-500">Loading…</p>
        ) : error ? (
          <p className="py-4 text-center text-xs text-red-400">{error}</p>
        ) : sorted.length === 0 ? (
          <p className="py-4 text-center text-xs text-slate-500">No crons</p>
        ) : (
          sorted.map((c) => (
            <CronCard key={c.id} cron={c} onClick={onCronClick} />
          ))
        )}
      </div>
    </div>
  );
}
