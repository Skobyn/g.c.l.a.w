"use client";

/**
 * Live-tail table of recent heartbeat events across all agents.
 */

import type { HeartbeatEvent, HeartbeatStatus } from "@/types";
import { truncate } from "@/components/admin/heartbeat-health-card";

interface HeartbeatEventListProps {
  events: HeartbeatEvent[];
}

const STATUS_TEXT: Record<HeartbeatStatus, string> = {
  sent: "text-green-400",
  "ok-token": "text-blue-400",
  "ok-empty": "text-slate-400",
  skipped: "text-yellow-400",
  failed: "text-red-400",
};

function formatTime(ts: string): string {
  try {
    return new Date(ts).toLocaleTimeString();
  } catch {
    return ts;
  }
}

export function HeartbeatEventList({ events }: HeartbeatEventListProps) {
  if (events.length === 0) {
    return (
      <p className="text-sm text-slate-500 italic px-4 py-6">
        No heartbeat events yet.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-700 bg-slate-900">
      <table className="min-w-full text-xs">
        <thead className="bg-slate-800 text-slate-400 uppercase tracking-wide">
          <tr>
            <th className="px-3 py-2 text-left font-semibold">Time</th>
            <th className="px-3 py-2 text-left font-semibold">Agent</th>
            <th className="px-3 py-2 text-left font-semibold">Status</th>
            <th className="px-3 py-2 text-left font-semibold">Reason</th>
            <th className="px-3 py-2 text-right font-semibold">Duration</th>
            <th className="px-3 py-2 text-left font-semibold">Preview / Error</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800">
          {events.map((e, i) => {
            const msg = e.error ?? e.preview ?? "";
            return (
              <tr
                key={`${e.timestamp}-${e.agent_id}-${i}`}
                className="hover:bg-slate-800/50 transition-colors"
              >
                <td className="px-3 py-1.5 text-slate-400 font-mono whitespace-nowrap">
                  {formatTime(e.timestamp)}
                </td>
                <td className="px-3 py-1.5 text-slate-200 whitespace-nowrap">
                  {e.agent_id}
                </td>
                <td
                  className={`px-3 py-1.5 font-semibold whitespace-nowrap ${STATUS_TEXT[e.status] ?? "text-slate-400"}`}
                >
                  {e.status}
                </td>
                <td className="px-3 py-1.5 text-slate-400 whitespace-nowrap">
                  {e.reason}
                </td>
                <td className="px-3 py-1.5 text-slate-400 text-right font-mono whitespace-nowrap">
                  {e.duration_ms}ms
                </td>
                <td
                  className={`px-3 py-1.5 font-mono ${e.error ? "text-red-400" : "text-slate-400"}`}
                >
                  {truncate(msg, 120)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
