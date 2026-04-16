"use client";

import Link from "next/link";
import type { AgentListEntry } from "@/types";
import { callNumber } from "@/lib/format";

interface AgentListCardProps {
  entry: AgentListEntry;
  index: number;
}

export function AgentListCard({ entry, index }: AgentListCardProps) {
  const name = entry.display_name || entry.name;
  const isOverridden = entry.has_override && !entry.is_standalone;

  return (
    <Link
      href={`/admin/agents/${encodeURIComponent(entry.name)}`}
      className="group relative grid grid-cols-[60px_1fr] gap-5 py-5 px-3 -mx-3 hairline-b transition-colors hover:bg-ink-800"
    >
      {/* Call number */}
      <div className="flex flex-col items-start">
        <span className="font-mono text-[22px] font-medium text-signal group-hover:text-signal transition-colors leading-none">
          {callNumber(index + 1)}
        </span>
        <span className="mt-1 font-mono text-[9px] uppercase tracking-[0.18em] text-paper-40">
          {entry.is_standalone ? "STANDALONE" : "BASELINE"}
        </span>
      </div>

      {/* Body */}
      <div className="min-w-0">
        <div className="flex items-baseline gap-3">
          <h3 className="font-display text-[18px] italic font-medium text-paper leading-none truncate">
            {name}
          </h3>
          <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-paper-40 truncate">
            {entry.name}
          </span>
        </div>

        {entry.description && (
          <p className="mt-2 font-body text-[13px] text-paper-60 line-clamp-2 leading-relaxed">
            {entry.description}
          </p>
        )}

        <div className="mt-3 flex flex-wrap items-center gap-3 font-mono text-[10px] uppercase tracking-[0.12em]">
          {entry.model_ref && (
            <span className="text-paper-60">
              <span className="text-paper-40">MODEL · </span>
              {entry.model_ref}
            </span>
          )}
          {entry.tools_profile && (
            <span className="text-paper-60">
              <span className="text-paper-40">TOOLS · </span>
              {entry.tools_profile}
            </span>
          )}
          <span className="flex items-center gap-1.5">
            {entry.heartbeat_enabled ? (
              <>
                <span className="phosphor-dot" />
                <span className="text-signal">HEARTBEAT LIVE</span>
              </>
            ) : (
              <span className="text-paper-40">HEARTBEAT · OFF</span>
            )}
          </span>
          {!entry.enabled && (
            <span className="text-alert">· DISABLED</span>
          )}
          {isOverridden && (
            <span className="text-gold">· OVERRIDDEN</span>
          )}
        </div>
      </div>
    </Link>
  );
}
