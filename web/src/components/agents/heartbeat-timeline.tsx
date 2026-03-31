"use client";

/**
 * Timeline of recent heartbeat log entries for an agent.
 */

import type { HeartbeatLogEntry } from "@/types";

interface HeartbeatTimelineProps {
  logs: HeartbeatLogEntry[];
}

function formatTimestamp(ts: string): string {
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

export function HeartbeatTimeline({ logs }: HeartbeatTimelineProps) {
  if (logs.length === 0) {
    return (
      <p className="text-sm text-slate-500 italic">No heartbeat logs available.</p>
    );
  }

  return (
    <ol className="relative space-y-4 border-l border-slate-700 pl-4">
      {logs.map((log) => (
        <li key={log.id} className="relative">
          {/* Timeline dot */}
          <span className="absolute -left-[1.35rem] top-1 h-3 w-3 rounded-full border-2 border-indigo-400 bg-slate-900" />

          <div className="rounded-md bg-slate-900 p-3 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs text-slate-400">{formatTimestamp(log.timestamp)}</span>
            </div>

            <p className="text-sm font-medium text-slate-200">{log.context_summary}</p>

            {log.reasoning && (
              <p className="text-xs text-slate-400 italic">{log.reasoning}</p>
            )}

            {log.actions_taken.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-indigo-400 mb-1">Actions taken:</p>
                <ul className="space-y-0.5">
                  {log.actions_taken.map((action, i) => (
                    <li key={i} className="text-xs text-slate-300 before:content-['•'] before:mr-1 before:text-indigo-400">
                      {action}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {log.tasks_created.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-slate-400 mb-1">Tasks created:</p>
                <ul className="space-y-0.5">
                  {log.tasks_created.map((task, i) => (
                    <li key={i} className="text-xs text-slate-300 before:content-['→'] before:mr-1 before:text-slate-500">
                      {task}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}
