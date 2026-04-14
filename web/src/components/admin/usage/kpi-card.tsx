"use client";

/** Big-number KPI card used in the usage dashboard. */

interface KpiCardProps {
  title: string;
  value: string;
  subtitle?: string;
  /** Tint the value text — e.g. 'text-amber-400' when cost is high. */
  valueClassName?: string;
  loading?: boolean;
}

export function KpiCard({
  title,
  value,
  subtitle,
  valueClassName,
  loading,
}: KpiCardProps) {
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/60 px-4 py-3">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
        {title}
      </div>
      {loading ? (
        <div className="mt-2 h-7 w-24 animate-pulse rounded bg-slate-800" />
      ) : (
        <div
          className={`mt-1 text-2xl font-bold tabular-nums ${
            valueClassName ?? "text-slate-100"
          }`}
        >
          {value}
        </div>
      )}
      {subtitle && (
        <div className="mt-0.5 text-xs text-slate-500">{subtitle}</div>
      )}
    </div>
  );
}
