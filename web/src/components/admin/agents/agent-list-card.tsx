"use client";

import Link from "next/link";
import type { AgentListEntry } from "@/types";

export function AgentListCard({ entry }: { entry: AgentListEntry }) {
  const name = entry.display_name || entry.name;
  const isOverridden = entry.has_override && !entry.is_standalone;

  return (
    <Link
      href={`/admin/agents/${encodeURIComponent(entry.name)}`}
      className="group flex flex-col gap-3 rounded-lg border border-slate-700 bg-slate-900/60 p-4 transition-colors hover:border-indigo-500 hover:bg-slate-900"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold text-slate-100">
            {name}
          </h3>
          <p className="mt-0.5 truncate font-mono text-[11px] text-slate-500">
            {entry.name}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-1">
          {entry.is_standalone && (
            <span className="rounded border border-teal-700 bg-teal-600/20 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-teal-300">
              custom
            </span>
          )}
          {isOverridden && (
            <span className="rounded border border-indigo-700 bg-indigo-600/20 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-indigo-300">
              overridden
            </span>
          )}
          {!entry.enabled && (
            <span className="rounded border border-slate-600 bg-slate-800 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-slate-400">
              off
            </span>
          )}
        </div>
      </div>

      {entry.description && (
        <p className="line-clamp-2 text-xs text-slate-400">
          {entry.description}
        </p>
      )}

      <div className="mt-auto flex flex-wrap items-center gap-1.5 text-[10px]">
        {entry.model_ref && (
          <span className="rounded border border-slate-600 bg-slate-800 px-1.5 py-0.5 font-mono text-slate-300">
            {entry.model_ref}
          </span>
        )}
        {entry.tools_profile && (
          <span className="rounded border border-purple-700 bg-purple-900/30 px-1.5 py-0.5 text-purple-300">
            tools: {entry.tools_profile}
          </span>
        )}
        <span
          className={`rounded border px-1.5 py-0.5 ${
            entry.heartbeat_enabled
              ? "border-green-700 bg-green-900/30 text-green-300"
              : "border-slate-600 bg-slate-800 text-slate-400"
          }`}
        >
          {entry.heartbeat_enabled ? "heartbeat on" : "heartbeat off"}
        </span>
      </div>
    </Link>
  );
}
