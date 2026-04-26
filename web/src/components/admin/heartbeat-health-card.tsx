"use client";

/**
 * Per-agent heartbeat health card.
 *
 * Renders for every registered agent, even ones with no heartbeat history.
 * Shows the most recent event summary when present (status, wake reason,
 * relative time, preview) and always exposes a "Send heartbeat" trigger.
 */

import { useState } from "react";
import type { AgentHealth, AgentListEntry, HeartbeatStatus } from "@/types";

interface HeartbeatHealthCardProps {
  health: AgentHealth;
  meta?: AgentListEntry | null;
  onTrigger?: (agentId: string) => void | Promise<void>;
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

export function HeartbeatHealthCard({
  health,
  meta,
  onTrigger,
}: HeartbeatHealthCardProps) {
  const status = health.last_status;
  const badge = status ? STATUS_STYLES[status] : null;
  const preview = truncate(health.last_preview ?? "", 60);
  const [busy, setBusy] = useState(false);

  const displayName =
    meta?.display_name && meta.display_name !== meta.name
      ? meta.display_name
      : null;
  const heartbeatConfigured = meta?.heartbeat_enabled === true;
  const agentDisabled = meta ? meta.enabled === false : false;

  async function handleTrigger() {
    if (!onTrigger || busy) return;
    setBusy(true);
    try {
      await onTrigger(health.agent_id);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900 p-4 flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-slate-100 truncate">
            {displayName ?? health.agent_id}
          </h3>
          {displayName && (
            <p className="font-mono text-[10px] text-slate-500 truncate">
              {health.agent_id}
            </p>
          )}
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

      {meta && (
        <div className="flex flex-wrap gap-1">
          <span
            className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-mono uppercase tracking-wide ${
              heartbeatConfigured
                ? "border-green-700 bg-green-600/10 text-green-400"
                : "border-slate-700 bg-slate-800 text-slate-500"
            }`}
            title={
              heartbeatConfigured
                ? "Heartbeat scheduled by config"
                : "No heartbeat configured — manual trigger only"
            }
          >
            HB {heartbeatConfigured ? "ON" : "OFF"}
          </span>
          {agentDisabled && (
            <span className="inline-flex items-center rounded border border-red-700 bg-red-600/10 px-1.5 py-0.5 text-[10px] font-mono uppercase tracking-wide text-red-400">
              DISABLED
            </span>
          )}
        </div>
      )}

      {preview ? (
        <p className="text-xs text-slate-400 line-clamp-2 font-mono break-words">
          {preview}
        </p>
      ) : (
        <p className="text-xs text-slate-600 italic">no preview</p>
      )}

      {onTrigger && (
        <button
          type="button"
          onClick={handleTrigger}
          disabled={busy}
          className="self-start rounded-md border border-slate-600 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {busy ? "Sending…" : "Send heartbeat"}
        </button>
      )}
    </div>
  );
}
