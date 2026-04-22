"use client";

/**
 * Modal editor for creating a new skill or editing an existing one.
 *
 * Only surfaces the fields that are meaningful for user-created skills:
 * name, description, version, trigger, tools required, agents granted,
 * and arbitrary JSON config. Built-in skills loaded from disk at startup
 * can still be edited here (e.g. to change which agents they're granted
 * to) — the changes persist in Firestore and survive restarts, but the
 * boot-time re-seed will overwrite them if the filesystem skill.json
 * changes. That trade-off is documented inline below.
 */

import { useEffect, useMemo, useState } from "react";
import type { SkillCreatePayload, SkillInfo } from "@/types";

interface Props {
  mode: "create" | "edit";
  initial: SkillInfo | null;
  existingNames: string[];
  onClose: () => void;
  onSave: (payload: SkillCreatePayload) => Promise<void>;
}

const TRIGGER_MODES: Array<"auto" | "manual" | "both"> = [
  "auto",
  "manual",
  "both",
];

const SOURCES: Array<"builtin" | "imported" | "custom"> = [
  "custom",
  "imported",
  "builtin",
];

export function SkillEditor({
  mode,
  initial,
  existingNames,
  onClose,
  onSave,
}: Props) {
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [version, setVersion] = useState(initial?.version ?? "1.0.0");
  const [triggerMode, setTriggerMode] = useState<"auto" | "manual" | "both">(
    initial?.trigger?.mode ?? "manual",
  );
  const [command, setCommand] = useState(initial?.trigger?.command ?? "");
  const [contexts, setContexts] = useState<string>(
    (initial?.trigger?.contexts ?? []).join(", "),
  );
  const [tools, setTools] = useState<string>(
    (initial?.tools_required ?? []).join(", "),
  );
  const [agents, setAgents] = useState<string>(
    (initial?.agents_granted ?? []).join(", "),
  );
  const [source, setSource] = useState<"builtin" | "imported" | "custom">(
    initial?.source ?? "custom",
  );
  const [configJson, setConfigJson] = useState<string>(
    JSON.stringify(initial?.config ?? {}, null, 2),
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
  }, [name, description, configJson]);

  const nameTaken = useMemo(() => {
    if (mode === "edit") return false;
    const trimmed = name.trim();
    return trimmed.length > 0 && existingNames.includes(trimmed);
  }, [name, existingNames, mode]);

  function parseList(raw: string): string[] {
    return raw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
  }

  async function handleSave() {
    if (!name.trim()) {
      setError("Name is required");
      return;
    }
    if (!description.trim()) {
      setError("Description is required");
      return;
    }
    if (nameTaken) {
      setError(`A skill named "${name.trim()}" already exists`);
      return;
    }
    let parsedConfig: Record<string, unknown> = {};
    try {
      const raw = configJson.trim() || "{}";
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        parsedConfig = parsed as Record<string, unknown>;
      } else {
        setError("Config must be a JSON object");
        return;
      }
    } catch (e) {
      setError(`Config JSON is invalid: ${e instanceof Error ? e.message : e}`);
      return;
    }

    const payload: SkillCreatePayload = {
      name: name.trim(),
      description: description.trim(),
      version: version.trim() || "1.0.0",
      trigger: {
        mode: triggerMode,
        contexts: parseList(contexts),
        command: command.trim() || null,
      },
      config: parsedConfig,
      tools_required: parseList(tools),
      agents_granted: parseList(agents),
      source,
    };

    setSaving(true);
    setError(null);
    try {
      await onSave(payload);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-[640px] max-h-[90vh] overflow-y-auto rounded-lg border border-slate-700 bg-slate-900 p-6 shadow-2xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-100">
            {mode === "create" ? "New skill" : `Edit ${initial?.name}`}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-200"
          >
            ×
          </button>
        </div>

        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-300">
              Name
            </label>
            <input
              className="w-full rounded-md border border-slate-600 bg-slate-950 px-3 py-1.5 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none disabled:opacity-60"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="content-quality-gate"
              spellCheck={false}
              disabled={mode === "edit"}
            />
            {nameTaken && (
              <p className="mt-1 text-xs text-amber-400">
                A skill with this name already exists.
              </p>
            )}
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-300">
              Description
            </label>
            <textarea
              className="w-full rounded-md border border-slate-600 bg-slate-950 px-3 py-1.5 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              placeholder="One-sentence summary of what this skill does and when to use it."
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-300">
                Version
              </label>
              <input
                className="w-full rounded-md border border-slate-600 bg-slate-950 px-3 py-1.5 text-sm text-slate-100"
                value={version}
                onChange={(e) => setVersion(e.target.value)}
                placeholder="1.0.0"
                spellCheck={false}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-300">
                Source
              </label>
              <select
                className="w-full rounded-md border border-slate-600 bg-slate-950 px-3 py-1.5 text-sm text-slate-100"
                value={source}
                onChange={(e) =>
                  setSource(e.target.value as "builtin" | "imported" | "custom")
                }
              >
                {SOURCES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-300">
              Trigger
            </label>
            <div className="grid grid-cols-3 gap-2">
              <select
                className="rounded-md border border-slate-600 bg-slate-950 px-3 py-1.5 text-sm text-slate-100"
                value={triggerMode}
                onChange={(e) =>
                  setTriggerMode(e.target.value as "auto" | "manual" | "both")
                }
              >
                {TRIGGER_MODES.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
              <input
                className="col-span-2 rounded-md border border-slate-600 bg-slate-950 px-3 py-1.5 text-sm text-slate-100"
                value={command}
                onChange={(e) => setCommand(e.target.value)}
                placeholder="Slash command (optional)"
                spellCheck={false}
              />
            </div>
            <input
              className="mt-2 w-full rounded-md border border-slate-600 bg-slate-950 px-3 py-1.5 text-sm text-slate-100"
              value={contexts}
              onChange={(e) => setContexts(e.target.value)}
              placeholder="Comma-separated trigger contexts"
              spellCheck={false}
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-300">
              Tools required
            </label>
            <input
              className="w-full rounded-md border border-slate-600 bg-slate-950 px-3 py-1.5 text-sm text-slate-100"
              value={tools}
              onChange={(e) => setTools(e.target.value)}
              placeholder="context_write, context_read_latest, generate_image"
              spellCheck={false}
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-300">
              Agents granted
            </label>
            <input
              className="w-full rounded-md border border-slate-600 bg-slate-950 px-3 py-1.5 text-sm text-slate-100"
              value={agents}
              onChange={(e) => setAgents(e.target.value)}
              placeholder="content-mgr, dev-mgr"
              spellCheck={false}
            />
            <p className="mt-1 text-[11px] text-slate-500">
              Leave blank to let per-agent overrides (on{" "}
              <span className="font-mono">/admin/agents/[name]</span>) decide
              who can use this skill.
            </p>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-300">
              Config (JSON)
            </label>
            <textarea
              className="w-full rounded-md border border-slate-600 bg-slate-950 px-3 py-1.5 font-mono text-xs text-slate-100"
              value={configJson}
              onChange={(e) => setConfigJson(e.target.value)}
              rows={6}
              spellCheck={false}
            />
          </div>

          {error && (
            <div className="rounded-md border border-red-700 bg-red-900/20 px-3 py-2 text-xs text-red-300">
              {error}
            </div>
          )}
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-600 px-4 py-1.5 text-sm text-slate-300 hover:bg-slate-800"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={saving}
            onClick={handleSave}
            className="rounded-md bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
