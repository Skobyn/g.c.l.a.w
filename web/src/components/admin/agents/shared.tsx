"use client";

/**
 * Shared UI for /admin/agents.
 */

import type { AgentOverride } from "@/types";

export const INPUT_CLS =
  "w-full rounded-md border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500";
export const LABEL_CLS = "block text-xs font-medium text-slate-400 mb-1";
export const SECTION_CLS =
  "rounded-lg border border-slate-700 bg-slate-900/60 p-5 space-y-4";

export function SaveBar({
  dirty,
  saving,
  onSave,
  onReset,
  error,
}: {
  dirty: boolean;
  saving: boolean;
  onSave: () => void;
  onReset?: () => void;
  error?: string | null;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3 border-t border-slate-700 pt-4">
      <button
        type="button"
        onClick={onSave}
        disabled={!dirty || saving}
        className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {saving ? "Saving..." : "Save"}
      </button>
      {onReset && (
        <button
          type="button"
          onClick={onReset}
          disabled={!dirty || saving}
          className="rounded-md border border-slate-600 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800 disabled:opacity-40"
        >
          Discard
        </button>
      )}
      {dirty && !saving && (
        <span className="text-xs text-amber-400">Unsaved changes</span>
      )}
      {error && <span className="text-xs text-red-400">{error}</span>}
    </div>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <label
      className={`flex items-center gap-2 text-sm text-slate-300 ${
        disabled ? "opacity-50" : "cursor-pointer"
      }`}
    >
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 rounded border-slate-600 bg-slate-900 text-indigo-500 focus:ring-indigo-500"
      />
      <span>{label}</span>
    </label>
  );
}

export function Banner({
  tone,
  children,
}: {
  tone: "yellow" | "red" | "blue" | "green" | "slate";
  children: React.ReactNode;
}) {
  const tones = {
    yellow: "border-amber-700 bg-amber-900/30 text-amber-200",
    red: "border-red-700 bg-red-900/30 text-red-300",
    blue: "border-blue-700 bg-blue-900/30 text-blue-200",
    green: "border-green-700 bg-green-900/30 text-green-200",
    slate: "border-slate-700 bg-slate-800/40 text-slate-300",
  };
  return (
    <div className={`rounded-md border px-4 py-2 text-sm ${tones[tone]}`}>
      {children}
    </div>
  );
}

export function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (a === null || b === null || a === undefined || b === undefined)
    return a === b;
  if (typeof a !== typeof b) return false;
  if (typeof a !== "object") return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  if (Array.isArray(a) && Array.isArray(b)) {
    if (a.length !== b.length) return false;
    for (let i = 0; i < a.length; i++) {
      if (!deepEqual(a[i], b[i])) return false;
    }
    return true;
  }
  const aKeys = Object.keys(a as object);
  const bKeys = Object.keys(b as object);
  if (aKeys.length !== bKeys.length) return false;
  for (const k of aKeys) {
    if (
      !deepEqual(
        (a as Record<string, unknown>)[k],
        (b as Record<string, unknown>)[k],
      )
    )
      return false;
  }
  return true;
}

export function summarizeOverride(ov: AgentOverride | null): string {
  if (!ov) return "No override";
  const parts: string[] = [];
  if (ov.identity.display_name) parts.push("identity");
  if (ov.model.primary || ov.model.thinking) parts.push("model");
  if (ov.tools.profile || ov.tools.allow.length || ov.tools.deny.length)
    parts.push("tools");
  if (ov.heartbeat) parts.push("heartbeat");
  if (ov.body_override || ov.system_prompt_override) parts.push("instructions");
  return parts.length === 0 ? "Override present (empty)" : parts.join(", ");
}
