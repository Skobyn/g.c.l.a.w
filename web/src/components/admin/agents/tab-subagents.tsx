"use client";

import { useEffect, useMemo, useState } from "react";
import type { AgentListEntry, AgentSubagentsSpec } from "@/types";
import {
  LABEL_CLS,
  SECTION_CLS,
  SaveBar,
  deepEqual,
} from "./shared";

type Mode = "inherit" | "any" | "allowlist";

function modeOf(value: AgentSubagentsSpec): Mode {
  if (value.allow === null) return "inherit";
  if (value.allow.length === 1 && value.allow[0] === "*") return "any";
  return "allowlist";
}

interface Props {
  value: AgentSubagentsSpec;
  allAgents: AgentListEntry[];
  selfName: string;
  onSave: (patch: { subagents: AgentSubagentsSpec }) => Promise<void>;
  onDirtyChange: (dirty: boolean) => void;
}

export function TabSubagents({
  value,
  allAgents,
  selfName,
  onSave,
  onDirtyChange,
}: Props) {
  const [mode, setMode] = useState<Mode>(modeOf(value));
  const [selected, setSelected] = useState<string[]>(
    value.allow && !(value.allow.length === 1 && value.allow[0] === "*")
      ? value.allow
      : [],
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setMode(modeOf(value));
    setSelected(
      value.allow && !(value.allow.length === 1 && value.allow[0] === "*")
        ? value.allow
        : [],
    );
  }, [value]);

  const computed: AgentSubagentsSpec = useMemo(() => {
    if (mode === "inherit") return { allow: null };
    if (mode === "any") return { allow: ["*"] };
    return { allow: selected };
  }, [mode, selected]);

  const dirty = !deepEqual(computed, value);
  useEffect(() => {
    onDirtyChange(dirty);
  }, [dirty, onDirtyChange]);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await onSave({ subagents: computed });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  const others = allAgents.filter((a) => a.name !== selfName);

  function toggle(name: string) {
    setSelected((prev) =>
      prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name],
    );
  }

  return (
    <section className={SECTION_CLS}>
      <h2 className="text-lg font-semibold text-slate-100">Subagents</h2>

      <div>
        <label className={LABEL_CLS}>Mode</label>
        <div className="flex flex-wrap gap-2">
          {(["inherit", "any", "allowlist"] as Mode[]).map((m) => (
            <label
              key={m}
              className={`cursor-pointer rounded-md border px-3 py-1.5 text-sm ${
                mode === m
                  ? "border-indigo-500 bg-indigo-600/20 text-indigo-200"
                  : "border-slate-600 text-slate-300 hover:bg-slate-800"
              }`}
            >
              <input
                type="radio"
                name="subagents-mode"
                className="sr-only"
                checked={mode === m}
                onChange={() => setMode(m)}
              />
              {m === "inherit"
                ? "Inherit default hierarchy"
                : m === "any"
                  ? "Any (*)"
                  : "Allowlist"}
            </label>
          ))}
        </div>
      </div>

      {mode === "allowlist" && (
        <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
          {others.map((a) => (
            <label
              key={a.name}
              className="flex cursor-pointer items-center gap-2 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm hover:border-slate-500"
            >
              <input
                type="checkbox"
                checked={selected.includes(a.name)}
                onChange={() => toggle(a.name)}
                className="h-4 w-4 rounded border-slate-600 bg-slate-900 text-indigo-500 focus:ring-indigo-500"
              />
              <span className="font-mono text-xs text-slate-200">{a.name}</span>
              {a.display_name && (
                <span className="text-[11px] text-slate-500">
                  · {a.display_name}
                </span>
              )}
            </label>
          ))}
        </div>
      )}

      <SaveBar
        dirty={dirty}
        saving={saving}
        onSave={save}
        onReset={() => {
          setMode(modeOf(value));
          setSelected(
            value.allow && !(value.allow.length === 1 && value.allow[0] === "*")
              ? value.allow
              : [],
          );
        }}
        error={error}
      />
    </section>
  );
}
