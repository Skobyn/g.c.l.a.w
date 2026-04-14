"use client";

/**
 * CronCard — renders a scheduled cron on the unified board.
 *
 * Shows schedule, next_run countdown, assignee and wake_mode. Clicking the
 * card invokes `onClick` which the parent uses to open the edit drawer.
 */

import type { CronInfo, ScheduleSpec } from "@/types";

interface CronCardProps {
  cron: CronInfo;
  onClick: (cron: CronInfo) => void;
}

function formatDurationMs(ms: number): string {
  if (ms % 86_400_000 === 0) return `${ms / 86_400_000}d`;
  if (ms % 3_600_000 === 0) return `${ms / 3_600_000}h`;
  if (ms % 60_000 === 0) return `${ms / 60_000}m`;
  if (ms % 1000 === 0) return `${ms / 1000}s`;
  return `${ms}ms`;
}

export function formatSchedule(schedule: ScheduleSpec | string | null | undefined): string {
  if (!schedule) return "—";
  if (typeof schedule === "string") return schedule;
  switch (schedule.kind) {
    case "cron":
      return schedule.expr;
    case "every":
      return `every ${formatDurationMs(schedule.every_ms)}`;
    case "at":
      try {
        return `at ${new Date(schedule.at).toLocaleString()}`;
      } catch {
        return `at ${schedule.at}`;
      }
    default:
      return JSON.stringify(schedule);
  }
}

/**
 * Human-readable countdown relative to now.
 *   future → "in 3h 12m"
 *   past   → "overdue 5m"
 */
export function formatCountdown(iso: string | null | undefined): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "—";
  const diff = t - Date.now();
  const abs = Math.abs(diff);
  const mins = Math.floor(abs / 60_000);
  const hrs = Math.floor(mins / 60);
  const days = Math.floor(hrs / 24);

  let parts: string;
  if (days >= 1) {
    const remHrs = hrs - days * 24;
    parts = remHrs > 0 ? `${days}d ${remHrs}h` : `${days}d`;
  } else if (hrs >= 1) {
    const remMins = mins - hrs * 60;
    parts = remMins > 0 ? `${hrs}h ${remMins}m` : `${hrs}h`;
  } else {
    parts = `${mins}m`;
  }

  return diff >= 0 ? `in ${parts}` : `overdue ${parts}`;
}

export function CronCard({ cron, onClick }: CronCardProps) {
  const paused = cron.status === "paused" || !cron.enabled;

  return (
    <button
      type="button"
      onClick={() => onClick(cron)}
      className={`w-full text-left rounded-lg border bg-slate-800 p-3 shadow-sm transition-colors ${
        paused
          ? "border-slate-700 opacity-60 hover:border-slate-500"
          : "border-slate-700 hover:border-indigo-500"
      }`}
    >
      {/* Top row: cron badge + title */}
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-medium text-slate-100 leading-snug line-clamp-2">
          {cron.title}
        </p>
        <span className="shrink-0 rounded bg-purple-900/60 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-purple-200 border border-purple-700">
          cron
        </span>
      </div>

      {/* Schedule */}
      <div className="mt-2">
        <code className="text-xs text-indigo-300 bg-slate-900 rounded px-1.5 py-0.5 break-all">
          {formatSchedule(cron.schedule)}
        </code>
      </div>

      {/* Countdown */}
      <div className="mt-2 flex items-center gap-2 text-xs">
        <span className="text-slate-400">next:</span>
        <span
          className={`font-medium ${
            cron.next_run && new Date(cron.next_run).getTime() < Date.now()
              ? "text-amber-300"
              : "text-slate-200"
          }`}
        >
          {paused ? "paused" : formatCountdown(cron.next_run)}
        </span>
      </div>

      {/* Footer row */}
      <div className="mt-2 flex items-center justify-between gap-2">
        <span className="text-xs text-slate-400 truncate max-w-[120px]">
          {cron.assignee || "unassigned"}
        </span>
        <div className="flex items-center gap-1">
          <span
            className={`inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-medium ${
              cron.wake_mode === "now"
                ? "bg-indigo-900/60 text-indigo-300"
                : "bg-purple-900/60 text-purple-300"
            }`}
            title={`wake_mode: ${cron.wake_mode}`}
          >
            {cron.wake_mode}
          </span>
          {paused && (
            <span className="inline-flex items-center rounded-full bg-slate-700 px-1.5 py-0.5 text-[10px] font-medium text-slate-300">
              paused
            </span>
          )}
        </div>
      </div>
    </button>
  );
}
