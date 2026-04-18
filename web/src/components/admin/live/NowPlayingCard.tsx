"use client";

/**
 * Shows the currently-active agent — agent name, model badge, status
 * chip, and in-flight tool chip. Pulses on Firestore update.
 */

import type { AgentRunDoc } from "@/hooks/useRunDoc";

interface NowPlayingCardProps {
  run: AgentRunDoc | null;
}

const STATUS_COLORS: Record<string, string> = {
  OK: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
  ERROR: "bg-red-500/20 text-red-300 border-red-500/40",
  UNSET: "bg-slate-500/20 text-slate-300 border-slate-600/40",
};

export function NowPlayingCard({ run }: NowPlayingCardProps) {
  const isEmpty = !run || !run.active_agent;
  const statusCls = STATUS_COLORS[run?.status || "UNSET"] || STATUS_COLORS.UNSET;

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/60 px-4 py-3">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
        Now playing
      </div>

      {isEmpty ? (
        <div className="mt-2 text-sm text-slate-500">No active run</div>
      ) : (
        <>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-2xl font-bold tabular-nums text-slate-100">
              {run!.active_agent}
            </span>
            {run!.model_id && (
              <span className="rounded border border-slate-700 bg-slate-800/80 px-2 py-0.5 text-[11px] font-mono text-slate-300">
                {run!.model_id}
              </span>
            )}
          </div>

          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
            <span
              className={`rounded border px-2 py-0.5 font-semibold uppercase tracking-wide ${statusCls}`}
            >
              {run!.status || "UNSET"}
            </span>
            {run!.tool_in_flight?.name && (
              <span className="rounded border border-amber-500/40 bg-amber-500/20 px-2 py-0.5 font-mono text-amber-300">
                tool:{run!.tool_in_flight.name}
              </span>
            )}
            {run!.provider && (
              <span className="text-slate-500">via {run!.provider}</span>
            )}
          </div>

          {run!.updated_at && (
            <div className="mt-2 text-[11px] text-slate-500">
              Updated {run!.updated_at}
            </div>
          )}
        </>
      )}
    </div>
  );
}
