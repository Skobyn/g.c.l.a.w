"use client";

import { useEffect, useState } from "react";
import {
  INPUT_CLS,
  LABEL_CLS,
  SECTION_CLS,
  SaveBar,
  Banner,
} from "./shared";

type Mode = "body" | "system";

interface Props {
  bodyOverride: string | null;
  systemPromptOverride: string | null;
  baseline: string;
  baselineError: string | null;
  onSave: (patch: {
    body_override?: string | null;
    system_prompt_override?: string | null;
  }) => Promise<void>;
  onDirtyChange: (dirty: boolean) => void;
}

export function TabInstructions({
  bodyOverride,
  systemPromptOverride,
  baseline,
  baselineError,
  onSave,
  onDirtyChange,
}: Props) {
  const [mode, setMode] = useState<Mode>(
    systemPromptOverride != null ? "system" : "body",
  );
  const [bodyLocal, setBodyLocal] = useState<string>(bodyOverride ?? "");
  const [systemLocal, setSystemLocal] = useState<string>(
    systemPromptOverride ?? "",
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showBaseline, setShowBaseline] = useState(false);

  useEffect(() => {
    setBodyLocal(bodyOverride ?? "");
    setSystemLocal(systemPromptOverride ?? "");
    setMode(systemPromptOverride != null ? "system" : "body");
  }, [bodyOverride, systemPromptOverride]);

  const dirty =
    mode === "body"
      ? (bodyLocal || null) !== bodyOverride
      : (systemLocal || null) !== systemPromptOverride;

  useEffect(() => {
    onDirtyChange(dirty);
  }, [dirty, onDirtyChange]);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      if (mode === "body") {
        await onSave({
          body_override: bodyLocal || null,
          system_prompt_override: null,
        });
      } else {
        await onSave({
          system_prompt_override: systemLocal || null,
          body_override: null,
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className={SECTION_CLS}>
      <h2 className="text-lg font-semibold text-slate-100">Instructions</h2>

      <div>
        <label className={LABEL_CLS}>Edit mode</label>
        <div className="flex flex-wrap gap-2">
          <label
            className={`cursor-pointer rounded-md border px-3 py-1.5 text-sm ${
              mode === "body"
                ? "border-indigo-500 bg-indigo-600/20 text-indigo-200"
                : "border-slate-600 text-slate-300 hover:bg-slate-800"
            }`}
          >
            <input
              type="radio"
              name="instr-mode"
              className="sr-only"
              checked={mode === "body"}
              onChange={() => setMode("body")}
            />
            Edit body
          </label>
          <label
            className={`cursor-pointer rounded-md border px-3 py-1.5 text-sm ${
              mode === "system"
                ? "border-indigo-500 bg-indigo-600/20 text-indigo-200"
                : "border-slate-600 text-slate-300 hover:bg-slate-800"
            }`}
          >
            <input
              type="radio"
              name="instr-mode"
              className="sr-only"
              checked={mode === "system"}
              onChange={() => setMode("system")}
            />
            Override full system prompt
          </label>
        </div>
      </div>

      {mode === "system" && (
        <Banner tone="yellow">
          Warning: setting a full system prompt override bypasses all frontmatter
          stitching (agent.md + soul.md + memory injections). Use only if you
          know what you&apos;re doing.
        </Banner>
      )}

      {mode === "body" ? (
        <div>
          <label className={LABEL_CLS}>Body override (markdown)</label>
          <textarea
            className={`${INPUT_CLS} font-mono`}
            style={{ height: 400 }}
            value={bodyLocal}
            onChange={(e) => setBodyLocal(e.target.value)}
            placeholder="Leave empty to inherit baseline body"
          />
        </div>
      ) : (
        <div>
          <label className={LABEL_CLS}>Full system prompt override</label>
          <textarea
            className={`${INPUT_CLS} font-mono`}
            style={{ height: 400 }}
            value={systemLocal}
            onChange={(e) => setSystemLocal(e.target.value)}
            placeholder="Exact system prompt text — will NOT be stitched with identity/soul."
          />
        </div>
      )}

      <div>
        <button
          type="button"
          onClick={() => setShowBaseline((v) => !v)}
          className="text-xs text-indigo-400 hover:text-indigo-300"
        >
          {showBaseline ? "▼ Hide baseline" : "▶ Show baseline"}
        </button>
        {showBaseline && (
          <div className="mt-2">
            {baselineError && (
              <p className="mb-2 text-xs text-red-400">{baselineError}</p>
            )}
            <pre className="max-h-80 overflow-auto rounded-md border border-slate-700 bg-slate-950 p-3 font-mono text-xs text-slate-300">
              {baseline || "(no baseline)"}
            </pre>
          </div>
        )}
      </div>

      <SaveBar
        dirty={dirty}
        saving={saving}
        onSave={save}
        onReset={() => {
          setBodyLocal(bodyOverride ?? "");
          setSystemLocal(systemPromptOverride ?? "");
          setMode(systemPromptOverride != null ? "system" : "body");
        }}
        error={error}
      />
    </section>
  );
}
