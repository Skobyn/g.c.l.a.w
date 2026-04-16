"use client";

/**
 * Shared UI for /admin/agents, phosphor-tuned.
 */

import type { AgentOverride } from "@/types";

export const INPUT_CLS =
  "w-full rounded-[3px] border border-paper-08 bg-ink-800 px-3 py-2 text-sm text-paper placeholder:text-paper-40 focus:border-signal focus:outline-none transition-colors";
export const LABEL_CLS =
  "block font-mono text-[10px] uppercase tracking-[0.14em] text-paper-40 mb-1.5";
export const SECTION_CLS =
  "rounded-[4px] border border-paper-08 bg-ink-800 p-5 space-y-4";

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
    <div className="flex flex-wrap items-center gap-3 hairline-t pt-4">
      <button
        type="button"
        onClick={onSave}
        disabled={!dirty || saving}
        className="btn-hair-signal"
      >
        {saving ? "Saving…" : "Save"}
      </button>
      {onReset && (
        <button
          type="button"
          onClick={onReset}
          disabled={!dirty || saving}
          className="btn-hair"
        >
          Discard
        </button>
      )}
      {dirty && !saving && (
        <span className="font-mono text-[10px] uppercase tracking-widest text-gold">
          UNSAVED CHANGES
        </span>
      )}
      {error && (
        <span className="font-mono text-[10px] uppercase tracking-widest text-alert">
          {error}
        </span>
      )}
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
      className={`inline-flex items-center gap-2 text-sm text-paper ${
        disabled ? "opacity-50" : "cursor-pointer"
      }`}
    >
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={`relative h-5 w-9 rounded-full border transition-colors ${
          checked
            ? "bg-signal-tint border-signal-dim"
            : "bg-ink-700 border-paper-15"
        }`}
      >
        <span
          className={`absolute top-0.5 h-3.5 w-3.5 rounded-full transition-[left,background] ${
            checked ? "left-[18px] bg-signal" : "left-0.5 bg-paper-40"
          }`}
          style={
            checked ? { boxShadow: "0 0 6px var(--signal)" } : undefined
          }
        />
      </button>
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
  const tones: Record<typeof tone, string> = {
    yellow: "border-gold/60 text-gold",
    red: "border-alert-dim text-alert",
    blue: "border-paper-15 text-paper-60",
    green: "border-signal-dim text-signal",
    slate: "border-paper-08 text-paper-60",
  };
  const bg: Record<typeof tone, string> = {
    yellow: "bg-gold/5",
    red: "bg-alert/5",
    blue: "bg-ink-800",
    green: "bg-signal-tint",
    slate: "bg-ink-800",
  };
  return (
    <div
      className={`rounded-[3px] border px-4 py-2.5 text-[13px] ${tones[tone]} ${bg[tone]}`}
    >
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
