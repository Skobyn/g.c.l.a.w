"use client";

/**
 * Radial context-window utilization gauge — used tokens / max tokens.
 *
 * Color bands:
 *   0-60%   green   (#22c55e)
 *   60-85%  amber   (#f59e0b)
 *   85-100% red     (#ef4444)
 */

import type { AgentRunDoc } from "@/hooks/useRunDoc";

interface ContextGaugeProps {
  run: AgentRunDoc | null;
}

const SIZE = 160;
const STROKE = 14;
const RADIUS = (SIZE - STROKE) / 2;
const CIRCUM = 2 * Math.PI * RADIUS;

function bandColor(pct: number): string {
  if (pct >= 0.85) return "#ef4444";
  if (pct >= 0.6) return "#f59e0b";
  return "#22c55e";
}

function fmtInt(n: number): string {
  return n.toLocaleString();
}

export function ContextGauge({ run }: ContextGaugeProps) {
  const used = run?.context_window?.used ?? run?.tokens?.in ?? 0;
  const max = run?.context_window?.max ?? 0;
  const rawPct =
    run?.context_window?.pct ?? (max > 0 ? used / max : 0);
  const pct = Math.max(0, Math.min(1, rawPct));
  const color = bandColor(pct);
  const dash = CIRCUM * pct;

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/60 px-4 py-3">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
        Context window
      </div>
      <div className="mt-1 flex items-center gap-4">
        <svg
          width={SIZE}
          height={SIZE}
          viewBox={`0 0 ${SIZE} ${SIZE}`}
          aria-label={`Context utilization ${(pct * 100).toFixed(1)} percent`}
        >
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            stroke="#1e293b"
            strokeWidth={STROKE}
            fill="none"
          />
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            stroke={color}
            strokeWidth={STROKE}
            fill="none"
            strokeLinecap="round"
            strokeDasharray={`${dash} ${CIRCUM - dash}`}
            transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}
          />
          <text
            x="50%"
            y="50%"
            dy="0.35em"
            textAnchor="middle"
            fill="#f1f5f9"
            className="font-bold tabular-nums"
            fontSize={24}
          >
            {(pct * 100).toFixed(1)}%
          </text>
        </svg>

        <div className="space-y-1 text-sm text-slate-300">
          <div>
            <span className="tabular-nums text-slate-100">{fmtInt(used)}</span>
            <span className="text-slate-500"> used</span>
          </div>
          <div>
            <span className="tabular-nums text-slate-100">
              {max > 0 ? fmtInt(max) : "—"}
            </span>
            <span className="text-slate-500"> max</span>
          </div>
          {max === 0 && (
            <div className="text-xs text-slate-500">
              Max unknown — run price-sync to populate context_window.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export const __test = { bandColor };
