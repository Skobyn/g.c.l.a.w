"use client";

/**
 * Running session cost with the last-turn delta as a ghost chip.
 */

import type { AgentRunDoc } from "@/hooks/useRunDoc";

interface CostTickerProps {
  run: AgentRunDoc | null;
}

function formatUsd(v: number | null | undefined): string {
  if (v == null) return "—";
  if (v >= 1000) return `$${v.toFixed(0)}`;
  if (v >= 1) return `$${v.toFixed(2)}`;
  return `$${v.toFixed(4)}`;
}

export function CostTicker({ run }: CostTickerProps) {
  const session = run?.cost_usd_session ?? null;
  const turn = run?.cost_usd_turn ?? null;

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/60 px-4 py-3">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
        Cost (session)
      </div>
      <div className="mt-1 flex items-baseline gap-3">
        <span className="text-2xl font-bold tabular-nums text-slate-100">
          {formatUsd(session)}
        </span>
        {turn != null && turn > 0 && (
          <span className="rounded border border-slate-700 bg-slate-800/80 px-2 py-0.5 text-[11px] font-mono text-slate-400">
            +{formatUsd(turn)} this turn
          </span>
        )}
      </div>
    </div>
  );
}

export const __test = { formatUsd };
