"use client";

/** Colored pill for a UsageKind. */

import type { UsageKind } from "@/types";

const CLASSES: Record<UsageKind, string> = {
  model: "border-indigo-700 bg-indigo-600/20 text-indigo-300",
  agent: "border-emerald-700 bg-emerald-600/20 text-emerald-300",
  skill: "border-amber-700 bg-amber-600/20 text-amber-300",
  tool: "border-rose-700 bg-rose-600/20 text-rose-300",
};

interface KindBadgeProps {
  kind: UsageKind;
}

export function KindBadge({ kind }: KindBadgeProps) {
  return (
    <span
      className={`rounded-md border px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${CLASSES[kind]}`}
    >
      {kind}
    </span>
  );
}
