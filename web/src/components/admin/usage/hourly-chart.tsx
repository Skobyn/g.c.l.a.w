"use client";

/**
 * Pure-SVG stacked bar chart of hourly usage activity with a cost overlay line.
 *
 * No chart libraries. Each hour renders as a stacked bar (model / agent /
 * skill / tool) with a cost polyline draped across the top on its own scale.
 * Hover highlights the bar and shows a tooltip with the full breakdown.
 */

import { useMemo, useState } from "react";
import type { UsageSummary } from "@/types";

interface HourlyChartProps {
  timeseries: UsageSummary["timeseries"];
  height?: number;
}

const COLORS = {
  model: "#6366f1", // indigo-500
  agent: "#10b981", // emerald-500
  skill: "#f59e0b", // amber-500
  tool: "#f43f5e", // rose-500
  cost: "#fbbf24", // amber-400
};

const LEGEND: Array<{ label: string; color: string }> = [
  { label: "Models", color: COLORS.model },
  { label: "Agents", color: COLORS.agent },
  { label: "Skills", color: COLORS.skill },
  { label: "Tools", color: COLORS.tool },
  { label: "Cost", color: COLORS.cost },
];

function formatHour(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}

function formatHourLong(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString([], {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function HourlyChart({ timeseries, height = 220 }: HourlyChartProps) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  const { maxEvents, maxCost } = useMemo(() => {
    let me = 0;
    let mc = 0;
    for (const row of timeseries) {
      const total =
        row.model_count + row.agent_count + row.skill_count + row.tool_count;
      if (total > me) me = total;
      if (row.cost_usd > mc) mc = row.cost_usd;
    }
    return { maxEvents: me || 1, maxCost: mc || 0 };
  }, [timeseries]);

  if (timeseries.length === 0) {
    return (
      <div className="flex items-center justify-center rounded-md border border-slate-700 bg-slate-900/60 px-4 py-12 text-center text-sm text-slate-500">
        <span>No events in this window yet.</span>
      </div>
    );
  }

  // Layout constants (viewBox coordinates). Width scales to container.
  const padL = 36;
  const padR = 40;
  const padT = 12;
  const padB = 24;
  const chartW = 800;
  const chartH = height;
  const innerW = chartW - padL - padR;
  const innerH = chartH - padT - padB;
  const bandW = innerW / timeseries.length;
  const barW = Math.max(2, bandW * 0.72);

  // Cost polyline points.
  const costPoints = timeseries
    .map((row, i) => {
      const cx = padL + bandW * (i + 0.5);
      const y =
        maxCost > 0
          ? padT + innerH - (row.cost_usd / maxCost) * innerH
          : padT + innerH;
      return `${cx.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/60 p-3">
      <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-400">
        {LEGEND.map((l) => (
          <span key={l.label} className="flex items-center gap-1.5">
            <span
              className="inline-block h-2 w-2 rounded-sm"
              style={{ background: l.color }}
            />
            {l.label}
          </span>
        ))}
        <span className="ml-auto text-[11px] text-slate-500">
          max events/hr: {maxEvents} · max cost/hr: ${maxCost.toFixed(2)}
        </span>
      </div>
      <div className="relative">
        <svg
          viewBox={`0 0 ${chartW} ${chartH}`}
          className="w-full"
          preserveAspectRatio="none"
          onMouseLeave={() => setHoverIdx(null)}
        >
          {/* Y-grid + axis labels (events scale). */}
          {[0, 0.25, 0.5, 0.75, 1].map((frac) => {
            const y = padT + innerH * (1 - frac);
            const label = Math.round(maxEvents * frac);
            return (
              <g key={frac}>
                <line
                  x1={padL}
                  x2={padL + innerW}
                  y1={y}
                  y2={y}
                  stroke="#334155"
                  strokeDasharray="2 3"
                  strokeWidth={0.5}
                />
                <text
                  x={padL - 4}
                  y={y + 3}
                  textAnchor="end"
                  fontSize={9}
                  fill="#64748b"
                >
                  {label}
                </text>
              </g>
            );
          })}
          {/* Right-side cost axis label. */}
          <text
            x={padL + innerW + 4}
            y={padT + 8}
            fontSize={9}
            fill="#fbbf24"
          >
            ${maxCost.toFixed(2)}
          </text>
          <text
            x={padL + innerW + 4}
            y={padT + innerH}
            fontSize={9}
            fill="#fbbf24"
          >
            $0
          </text>

          {/* Bars (stacked). */}
          {timeseries.map((row, i) => {
            const total =
              row.model_count +
              row.agent_count +
              row.skill_count +
              row.tool_count;
            const x = padL + bandW * i + (bandW - barW) / 2;
            let yCursor = padT + innerH;
            const parts: Array<{ count: number; color: string }> = [
              { count: row.model_count, color: COLORS.model },
              { count: row.agent_count, color: COLORS.agent },
              { count: row.skill_count, color: COLORS.skill },
              { count: row.tool_count, color: COLORS.tool },
            ];
            const isHover = hoverIdx === i;
            return (
              <g
                key={row.hour_iso}
                onMouseEnter={() => setHoverIdx(i)}
                style={{ cursor: "default" }}
              >
                {/* Hit area spanning full band for easier hover. */}
                <rect
                  x={padL + bandW * i}
                  y={padT}
                  width={bandW}
                  height={innerH}
                  fill="transparent"
                />
                {parts.map((p, pi) => {
                  if (p.count <= 0) return null;
                  const h = (p.count / maxEvents) * innerH;
                  yCursor -= h;
                  return (
                    <rect
                      key={pi}
                      x={x}
                      y={yCursor}
                      width={barW}
                      height={h}
                      fill={p.color}
                      opacity={isHover ? 1 : 0.85}
                    />
                  );
                })}
                {total === 0 && (
                  <rect
                    x={x}
                    y={padT + innerH - 1}
                    width={barW}
                    height={1}
                    fill="#334155"
                  />
                )}
              </g>
            );
          })}

          {/* Cost overlay polyline. */}
          {maxCost > 0 && (
            <polyline
              points={costPoints}
              fill="none"
              stroke={COLORS.cost}
              strokeWidth={1.5}
              strokeLinejoin="round"
              strokeLinecap="round"
              opacity={0.9}
            />
          )}

          {/* X-axis tick labels (sparse). */}
          {timeseries.map((row, i) => {
            const step = Math.max(1, Math.floor(timeseries.length / 8));
            if (i % step !== 0 && i !== timeseries.length - 1) return null;
            const cx = padL + bandW * (i + 0.5);
            return (
              <text
                key={`t-${row.hour_iso}`}
                x={cx}
                y={chartH - 8}
                textAnchor="middle"
                fontSize={9}
                fill="#64748b"
              >
                {formatHour(row.hour_iso)}
              </text>
            );
          })}
        </svg>

        {/* Tooltip. */}
        {hoverIdx !== null && timeseries[hoverIdx] && (
          <div
            className="pointer-events-none absolute rounded-md border border-slate-600 bg-slate-950/95 px-3 py-2 text-xs text-slate-200 shadow-lg"
            style={{
              left: `${((hoverIdx + 0.5) / timeseries.length) * 100}%`,
              top: 4,
              transform: "translateX(-50%)",
              minWidth: 160,
            }}
          >
            <div className="mb-1 border-b border-slate-700 pb-1 text-[11px] text-slate-400">
              {formatHourLong(timeseries[hoverIdx].hour_iso)}
            </div>
            <TooltipRow
              color={COLORS.model}
              label="Models"
              value={timeseries[hoverIdx].model_count}
            />
            <TooltipRow
              color={COLORS.agent}
              label="Agents"
              value={timeseries[hoverIdx].agent_count}
            />
            <TooltipRow
              color={COLORS.skill}
              label="Skills"
              value={timeseries[hoverIdx].skill_count}
            />
            <TooltipRow
              color={COLORS.tool}
              label="Tools"
              value={timeseries[hoverIdx].tool_count}
            />
            <div className="mt-1 border-t border-slate-700 pt-1">
              <TooltipRow
                color={COLORS.cost}
                label="Cost"
                value={`$${timeseries[hoverIdx].cost_usd.toFixed(4)}`}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function TooltipRow({
  color,
  label,
  value,
}: {
  color: string;
  label: string;
  value: number | string;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="flex items-center gap-1.5">
        <span
          className="inline-block h-2 w-2 rounded-sm"
          style={{ background: color }}
        />
        {label}
      </span>
      <span className="tabular-nums text-slate-100">{value}</span>
    </div>
  );
}
