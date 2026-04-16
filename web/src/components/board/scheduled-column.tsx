"use client";

/**
 * ScheduledColumn — leftmost "Scheduled" newspaper column of the board.
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
    <div className="flex w-[260px] shrink-0 flex-col">
      <div className="pb-2 border-b-2 border-hair">
        <div className="flex items-baseline justify-between">
          <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-gold">
            SCHEDULED
          </span>
          <span className="font-mono text-[10px] text-paper-40">
            ({crons.length.toString().padStart(2, "0")})
          </span>
        </div>
      </div>

      <div className="flex flex-1 flex-col overflow-y-auto px-1">
        {loading && crons.length === 0 ? (
          <p className="py-6 text-center font-mono text-[10px] uppercase tracking-widest text-paper-40">
            LOADING…
          </p>
        ) : error ? (
          <p className="py-6 text-center font-mono text-[10px] uppercase tracking-widest text-alert">
            {error}
          </p>
        ) : sorted.length === 0 ? (
          <p className="py-6 text-center font-mono text-[10px] uppercase tracking-widest text-paper-40">
            — no crons —
          </p>
        ) : (
          sorted.map((c) => (
            <CronCard key={c.id} cron={c} onClick={onCronClick} />
          ))
        )}
      </div>
    </div>
  );
}
