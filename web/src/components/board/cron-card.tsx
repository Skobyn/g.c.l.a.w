"use client";

/**
 * CronCard — typeset scheduled entry with a phosphor glyph.
 *
 *   ◎ Title in paper, semibold
 *     cron expr · next run · assignee
 *     paused overlay when disabled
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

export function formatSchedule(
  schedule: ScheduleSpec | string | null | undefined,
): string {
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
  const overdue =
    !!cron.next_run && new Date(cron.next_run).getTime() < Date.now();

  return (
    <button
      type="button"
      onClick={() => onClick(cron)}
      className={`w-full text-left py-3 px-3 -mx-1 hairline-b transition-colors ${
        paused ? "opacity-55" : ""
      } hover:bg-ink-800`}
    >
      <div className="flex items-start gap-2">
        <span
          className={`mt-0.5 text-[14px] leading-none ${
            paused ? "text-paper-40" : "text-signal"
          }`}
        >
          ◎
        </span>
        <div className="min-w-0 flex-1">
          <p className="font-body text-[13.5px] font-medium text-paper leading-snug line-clamp-2">
            {cron.title}
          </p>
          <p className="mt-1.5 font-mono text-[10px] uppercase tracking-[0.1em] text-paper-60 truncate">
            {formatSchedule(cron.schedule)}
          </p>
          <p className="mt-0.5 font-mono text-[10px] uppercase tracking-[0.1em] text-paper-40">
            <span
              className={
                overdue && !paused
                  ? "text-alert"
                  : paused
                    ? "text-paper-40"
                    : "text-paper-60"
              }
            >
              {paused ? "PAUSED" : formatCountdown(cron.next_run)}
            </span>
            <span className="mx-1">·</span>
            <span className="text-paper-60 truncate">
              {cron.assignee || "unassigned"}
            </span>
          </p>
        </div>
      </div>
    </button>
  );
}
