"use client";

/**
 * Running in/out token counters for the current agent run. Cached
 * reads are broken out separately when the backend reports them.
 */

import type { AgentRunDoc } from "@/hooks/useRunDoc";

interface TokenMeterProps {
  run: AgentRunDoc | null;
}

function fmt(n: number | null | undefined): string {
  return n == null ? "—" : n.toLocaleString();
}

export function TokenMeter({ run }: TokenMeterProps) {
  const tokIn = run?.tokens?.in ?? null;
  const tokOut = run?.tokens?.out ?? null;
  const tokTotal = run?.tokens?.total ?? null;
  const cacheRead = run?.tokens?.cache_read ?? null;

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/60 px-4 py-3">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
        Tokens
      </div>

      <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm tabular-nums">
        <div className="text-slate-500">in</div>
        <div className="text-right text-slate-100">{fmt(tokIn)}</div>

        <div className="text-slate-500">out</div>
        <div className="text-right text-slate-100">{fmt(tokOut)}</div>

        <div className="text-slate-500">total</div>
        <div className="text-right font-semibold text-slate-100">
          {fmt(tokTotal)}
        </div>

        {cacheRead != null && cacheRead > 0 && (
          <>
            <div className="text-emerald-500">cache read</div>
            <div className="text-right text-emerald-300">{fmt(cacheRead)}</div>
          </>
        )}
      </div>
    </div>
  );
}
