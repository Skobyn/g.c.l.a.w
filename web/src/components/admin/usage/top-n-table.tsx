"use client";

/** Config-driven Top-N table. */

import type { ReactNode } from "react";

export interface TopNColumn<T> {
  header: string;
  cell: (row: T) => ReactNode;
  align?: "left" | "right";
  className?: string;
}

interface TopNTableProps<T> {
  title: string;
  rows: T[];
  columns: TopNColumn<T>[];
  emptyLabel?: string;
  loading?: boolean;
}

export function TopNTable<T>({
  title,
  rows,
  columns,
  emptyLabel = "No data in this window.",
  loading,
}: TopNTableProps<T>) {
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/60">
      <div className="border-b border-slate-700 px-4 py-2 text-sm font-semibold text-slate-200">
        {title}
      </div>
      {loading ? (
        <div className="p-4 space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div
              key={i}
              className="h-4 w-full animate-pulse rounded bg-slate-800"
            />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <div className="px-4 py-8 text-center text-sm text-slate-500">
          {emptyLabel}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wide text-slate-500">
                {columns.map((c, i) => (
                  <th
                    key={i}
                    className={`px-4 py-2 font-medium ${
                      c.align === "right" ? "text-right" : ""
                    }`}
                  >
                    {c.header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, ri) => (
                <tr
                  key={ri}
                  className="border-t border-slate-800 text-slate-300 hover:bg-slate-800/40"
                >
                  {columns.map((c, ci) => (
                    <td
                      key={ci}
                      className={`px-4 py-2 ${
                        c.align === "right" ? "text-right tabular-nums" : ""
                      } ${c.className ?? ""}`}
                    >
                      {c.cell(row)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
