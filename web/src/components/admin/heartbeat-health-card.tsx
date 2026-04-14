"use client";

/**
 * Per-agent heartbeat health card.
 *
 * Shows the most recent event summary: status, wake reason, relative time,
 * and a truncated preview or error message.
 */

import type { AgentHealth, HeartbeatStatus } from "@/types";

interface HeartbeatHealthCardProps {
  health: AgentHealth;
  onTrigger?: (agentId: string) => void;
}

const STATUS_STYLES: Record<HeartbeatStatus, { label: string; classes: string }> = {
  sent: { label: "SENT", classes: "bg-green-600/20 text-green-400 border-green-700" },
  "ok-token": { label: "OK_TOKEN", classes: "bg-blue-600/20 text-blue-400 border-blue-700" },
  "ok-empty": { label: "OK_EMPTY", classes: "bg-slate-600/30 text-slate-300 border-slate-600" },
  skipped: { label: "SKIPPED", classes: "bg-yellow-600/20 text-yellow-400 border-yellow-700" },
  failed: { label: "FAILED", classes: "bg-red-600/20 text-red-400 border-red-700" },
};

export function formatRelative(ts: string | null): string {
  if (!ts) return "never";
  const then = new Date(ts).getTime();
  if (Number.isNaN(then)) return ts;
  const diffSec = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (diffSec < 5) return "just now";
  if (diffSec < 60) return `${diffSec}s ago`;
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  return `${Math.floor(diffSec / 86400)}d ago`;
}

export function truncate(s: string, n: number): string {
  if (!s) return "";
  return s.length > n ? s.slice(0, n) + "…" : s;
}

export function HeartbeatHealthCard({ health, onTrigger }: HeartbeatHealthCardProps) {
  const status = health.last_status;
  const badge = status ? STATUS_STYLES[status] : null;
  const preview = truncate(health.last_preview ?? "", 60);

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900 p-4 flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-slate-100 truncate">
            {health.agent_id}
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            {formatRelative(health.last_event_at)}
            {health.last_reason && (
              <>
                {" · "}
                <span className="text-slate-400">{health.last_reason}</span>
              </>
            )}
          </p>
        </div>
        {badge ? (
          <span
            className={`shrink-0 rounded-md border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${badge.classes}`}
          >
            {badge.label}
          </span>
        ) : (
          <span className="shrink-0 rounded-md border border-slate-700 bg-slate-800 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-slate-500">
            NO DATA
          </span>
        )}
      </div>

      {preview ? (
        <p className="text-xs text-slate-400 line-clamp-2 font-mono break-words">
          {preview}
        </p>
      ) : (
        <p className="text-xs text-slate-600 italic">no preview</p>
      )}

      {/* TODO: wire "Trigger now" once backend exposes a manual heartbeat trigger endpoint. */}
      {onTrigger && (
        <button
          onClick={() => onTrigger(health.agent_id)}
          className="self-start rounded-md border border-slate-600 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800 transition-colors"
        >
          Trigger now
        </button>
      )}
    </div>
  );
}
