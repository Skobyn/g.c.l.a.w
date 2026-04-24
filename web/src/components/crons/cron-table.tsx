"use client";

/**
 * Table displaying cron jobs with toggle and trigger actions.
 */

import type { CronInfo, ScheduleSpec } from "@/types";

interface CronTableProps {
  crons: CronInfo[];
  onToggle: (cronId: string) => void;
  onTrigger: (cronId: string) => void;
  togglingId: string | null;
  triggeringId: string | null;
  /** Optional — wire to open the CronEditDrawer on a chosen cron. */
  onEdit?: (cron: CronInfo) => void;
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "—";
  try {
    return new Date(dateStr).toLocaleString();
  } catch {
    return dateStr;
  }
}

function formatDurationMs(ms: number): string {
  if (ms % 86_400_000 === 0) return `${ms / 86_400_000}d`;
  if (ms % 3_600_000 === 0) return `${ms / 3_600_000}h`;
  if (ms % 60_000 === 0) return `${ms / 60_000}m`;
  if (ms % 1000 === 0) return `${ms / 1000}s`;
  return `${ms}ms`;
}

function formatSchedule(schedule: ScheduleSpec | string | undefined | null): string {
  if (!schedule) return "—";
  if (typeof schedule === "string") return schedule;
  switch (schedule.kind) {
    case "cron":
      return schedule.expr;
    case "every":
      return `every ${formatDurationMs(schedule.every_ms)}`;
    case "at":
      return `at ${formatDate(schedule.at)}`;
    default:
      return JSON.stringify(schedule);
  }
}

export function CronTable({
  crons,
  onToggle,
  onTrigger,
  togglingId,
  triggeringId,
  onEdit,
}: CronTableProps) {
  if (crons.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-slate-500">
        <svg className="h-12 w-12 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <p className="text-sm">No cron jobs configured</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-700">
      <table className="min-w-full divide-y divide-slate-700">
        <thead className="bg-slate-800">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400">Title</th>
            <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400">Schedule</th>
            <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400">Payload</th>
            <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400">Wake</th>
            <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400">Mode</th>
            <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400">Assignee</th>
            <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400">Status</th>
            <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400">Last Run</th>
            <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-slate-400">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-700 bg-slate-900">
          {crons.map((cron) => (
            <tr key={cron.id} className="hover:bg-slate-800/50 transition-colors">
              {/* Title + description */}
              <td className="px-4 py-3">
                <p className="font-medium text-slate-100 text-sm">{cron.title}</p>
                {cron.description && (
                  <p className="text-xs text-slate-400 mt-0.5 line-clamp-1">{cron.description}</p>
                )}
              </td>

              {/* Schedule */}
              <td className="px-4 py-3">
                <code className="text-xs text-indigo-300 bg-slate-800 rounded px-1.5 py-0.5">
                  {formatSchedule(cron.schedule)}
                </code>
              </td>

              {/* Payload kind */}
              <td className="px-4 py-3">
                <span className="inline-flex items-center rounded-full bg-slate-800 px-2 py-0.5 text-xs font-medium text-slate-300">
                  {cron.payload?.kind ?? "—"}
                </span>
              </td>

              {/* Wake mode */}
              <td className="px-4 py-3">
                <span
                  className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                    cron.wake_mode === "now"
                      ? "bg-indigo-900/60 text-indigo-300"
                      : "bg-purple-900/60 text-purple-300"
                  }`}
                >
                  {cron.wake_mode ?? "—"}
                </span>
              </td>

              {/* Mode */}
              <td className="px-4 py-3">
                <span
                  className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                    cron.mode === "auto"
                      ? "bg-green-900/60 text-green-300"
                      : "bg-blue-900/60 text-blue-300"
                  }`}
                >
                  {cron.mode}
                </span>
              </td>

              {/* Assignee */}
              <td className="px-4 py-3 text-sm text-slate-300">{cron.assignee}</td>

              {/* Status */}
              <td className="px-4 py-3">
                <div className="flex items-center gap-1.5">
                  <span
                    className={`h-2 w-2 rounded-full ${
                      cron.status === "active" ? "bg-green-400" : "bg-slate-500"
                    }`}
                  />
                  <span className="text-sm text-slate-300">{cron.status}</span>
                </div>
              </td>

              {/* Last run */}
              <td className="px-4 py-3 text-xs text-slate-400">{formatDate(cron.last_run)}</td>

              {/* Actions */}
              <td className="px-4 py-3 text-right">
                <div className="flex items-center justify-end gap-2">
                  {onEdit && (
                    <button
                      onClick={() => onEdit(cron)}
                      className="rounded px-2 py-1 text-xs font-medium text-indigo-300 border border-indigo-700 hover:bg-indigo-900/30 transition-colors"
                      title="Edit cron"
                    >
                      Edit
                    </button>
                  )}
                  <button
                    onClick={() => onTrigger(cron.id)}
                    disabled={triggeringId === cron.id}
                    className="rounded px-2 py-1 text-xs font-medium text-slate-300 border border-slate-600 hover:bg-slate-700 disabled:opacity-50 transition-colors"
                    title="Trigger now"
                  >
                    {triggeringId === cron.id ? "Running..." : "Run"}
                  </button>
                  <button
                    onClick={() => onToggle(cron.id)}
                    disabled={togglingId === cron.id}
                    className={`rounded px-2 py-1 text-xs font-medium border transition-colors disabled:opacity-50 ${
                      cron.status === "active"
                        ? "text-yellow-300 border-yellow-700 hover:bg-yellow-900/30"
                        : "text-green-300 border-green-700 hover:bg-green-900/30"
                    }`}
                    title={cron.status === "active" ? "Pause" : "Resume"}
                  >
                    {togglingId === cron.id
                      ? "..."
                      : cron.status === "active"
                      ? "Pause"
                      : "Resume"}
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
