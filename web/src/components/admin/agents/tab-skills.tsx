"use client";

import { useEffect, useState } from "react";
import type { SkillInfo } from "@/types";
import {
  LABEL_CLS,
  SECTION_CLS,
  SaveBar,
  deepEqual,
} from "./shared";

type Mode = "inherit" | "none" | "allowlist";

function modeOf(value: string[] | null): Mode {
  if (value === null) return "inherit";
  if (value.length === 0) return "none";
  return "allowlist";
}

interface Props {
  value: string[] | null;
  skills: SkillInfo[];
  skillsError: string | null;
  onSave: (patch: { skills: string[] | null }) => Promise<void>;
  onDirtyChange: (dirty: boolean) => void;
}

export function TabSkills({
  value,
  skills,
  skillsError,
  onSave,
  onDirtyChange,
}: Props) {
  const [mode, setMode] = useState<Mode>(modeOf(value));
  const [selected, setSelected] = useState<string[]>(value ?? []);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setMode(modeOf(value));
    setSelected(value ?? []);
  }, [value]);

  const computed: string[] | null =
    mode === "inherit" ? null : mode === "none" ? [] : selected;

  const dirty = !deepEqual(computed, value);
  useEffect(() => {
    onDirtyChange(dirty);
  }, [dirty, onDirtyChange]);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await onSave({ skills: computed });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  function toggle(name: string) {
    setSelected((prev) =>
      prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name],
    );
  }

  return (
    <section className={SECTION_CLS}>
      <h2 className="text-lg font-semibold text-slate-100">Skills</h2>

      <div>
        <label className={LABEL_CLS}>Mode</label>
        <div className="flex flex-wrap gap-2">
          {(["inherit", "none", "allowlist"] as Mode[]).map((m) => (
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
                name="skills-mode"
                className="sr-only"
                checked={mode === m}
                onChange={() => setMode(m)}
              />
              {m === "inherit"
                ? "Inherit (default)"
                : m === "none"
                  ? "All disabled"
                  : "Allowlist"}
            </label>
          ))}
        </div>
      </div>

      {mode === "allowlist" && (
        <div>
          {skillsError && (
            <p className="mb-2 text-xs text-red-400">
              Skill catalog unavailable: {skillsError}. Using free-form chips
              below.
            </p>
          )}
          {skills.length === 0 ? (
            <p className="text-xs text-slate-500">
              No skills discovered. Add names as strings:
            </p>
          ) : (
            <>
              <div className="mb-2 flex items-center justify-between text-xs text-slate-400">
                <span>
                  {selected.length} of {skills.length} selected
                </span>
                <div className="flex gap-3">
                  <button
                    type="button"
                    className="text-indigo-300 hover:text-indigo-200 disabled:opacity-50"
                    onClick={() => setSelected(skills.map((s) => s.name))}
                    disabled={selected.length === skills.length}
                  >
                    Select all available
                  </button>
                  <button
                    type="button"
                    className="text-slate-300 hover:text-slate-100 disabled:opacity-50"
                    onClick={() => setSelected([])}
                    disabled={selected.length === 0}
                  >
                    Clear
                  </button>
                </div>
              </div>
              <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
                {skills.map((s) => (
                <label
                  key={s.name}
                  className="flex cursor-pointer items-start gap-2 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm hover:border-slate-500"
                >
                  <input
                    type="checkbox"
                    checked={selected.includes(s.name)}
                    onChange={() => toggle(s.name)}
                    className="mt-0.5 h-4 w-4 rounded border-slate-600 bg-slate-900 text-indigo-500 focus:ring-indigo-500"
                  />
                  <div className="min-w-0">
                    <div className="font-mono text-xs text-slate-200">
                      {s.name}
                    </div>
                    <div className="truncate text-[11px] text-slate-500">
                      {s.description}
                    </div>
                  </div>
                </label>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      <SaveBar
        dirty={dirty}
        saving={saving}
        onSave={save}
        onReset={() => {
          setMode(modeOf(value));
          setSelected(value ?? []);
        }}
        error={error}
      />
    </section>
  );
}
