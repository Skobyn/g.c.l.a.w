"use client";

import { useEffect, useMemo, useState } from "react";
import type {
  AgentModelSpec,
  CatalogModel,
  ThinkingLevel,
} from "@/types";
import { ChipInput } from "./chip-input";
import {
  INPUT_CLS,
  LABEL_CLS,
  SECTION_CLS,
  SaveBar,
  deepEqual,
} from "./shared";

const THINKING_LEVELS: ThinkingLevel[] = [
  "off",
  "minimal",
  "low",
  "medium",
  "high",
  "xhigh",
  "adaptive",
];

interface Props {
  value: AgentModelSpec;
  models: CatalogModel[];
  onSave: (patch: { model: AgentModelSpec }) => Promise<void>;
  onDirtyChange: (dirty: boolean) => void;
}

type ParamRow = { key: string; value: string };

function paramsToRows(params: Record<string, unknown>): ParamRow[] {
  return Object.entries(params).map(([k, v]) => ({
    key: k,
    value: typeof v === "string" ? v : JSON.stringify(v),
  }));
}

function rowsToParams(rows: ParamRow[]): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const r of rows) {
    if (!r.key) continue;
    const raw = r.value;
    // try to parse as JSON first
    if (raw === "") continue;
    try {
      out[r.key] = JSON.parse(raw);
    } catch {
      out[r.key] = raw;
    }
  }
  return out;
}

export function TabModel({ value, models, onSave, onDirtyChange }: Props) {
  const [local, setLocal] = useState<AgentModelSpec>(value);
  const [paramRows, setParamRows] = useState<ParamRow[]>(
    paramsToRows(value.params),
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLocal(value);
    setParamRows(paramsToRows(value.params));
  }, [value]);

  const computed: AgentModelSpec = useMemo(
    () => ({ ...local, params: rowsToParams(paramRows) }),
    [local, paramRows],
  );

  const dirty = !deepEqual(computed, value);
  useEffect(() => {
    onDirtyChange(dirty);
  }, [dirty, onDirtyChange]);

  const modelOptions = useMemo(
    () =>
      models.map((m) => ({
        value: m.model_id,
        label: `${m.display_name} (${m.model_id})`,
      })),
    [models],
  );

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await onSave({ model: computed });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className={SECTION_CLS}>
      <h2 className="text-lg font-semibold text-slate-100">Model</h2>

      <div>
        <label className={LABEL_CLS}>Primary model</label>
        <input
          type="text"
          className={INPUT_CLS}
          list="model-options"
          value={local.primary ?? ""}
          onChange={(e) =>
            setLocal({ ...local, primary: e.target.value || null })
          }
          placeholder="model_id (free-form or pick from catalog)"
        />
        <datalist id="model-options">
          {modelOptions.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </datalist>
      </div>

      <div>
        <label className={LABEL_CLS}>Fallbacks</label>
        <ChipInput
          values={local.fallbacks}
          onChange={(v) => setLocal({ ...local, fallbacks: v })}
          placeholder="Add fallback model_id and press Enter"
        />
      </div>

      <div>
        <label className={LABEL_CLS}>Thinking</label>
        <select
          className={INPUT_CLS}
          value={local.thinking ?? ""}
          onChange={(e) =>
            setLocal({
              ...local,
              thinking: (e.target.value || null) as ThinkingLevel | null,
            })
          }
        >
          <option value="">(inherit)</option>
          {THINKING_LEVELS.map((l) => (
            <option key={l} value={l}>
              {l}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className={LABEL_CLS}>Params</label>
        <div className="space-y-2">
          {paramRows.map((row, i) => (
            <div key={i} className="flex gap-2">
              <input
                className={`${INPUT_CLS} w-48`}
                placeholder="key (e.g. temperature)"
                value={row.key}
                onChange={(e) => {
                  const next = paramRows.slice();
                  next[i] = { ...row, key: e.target.value };
                  setParamRows(next);
                }}
              />
              <input
                className={`${INPUT_CLS} flex-1`}
                placeholder="value (JSON or string)"
                value={row.value}
                onChange={(e) => {
                  const next = paramRows.slice();
                  next[i] = { ...row, value: e.target.value };
                  setParamRows(next);
                }}
              />
              <button
                type="button"
                onClick={() =>
                  setParamRows(paramRows.filter((_, j) => j !== i))
                }
                className="rounded-md border border-slate-600 px-2 text-xs text-slate-400 hover:bg-red-900/40 hover:text-red-300"
              >
                ×
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={() => setParamRows([...paramRows, { key: "", value: "" }])}
            className="rounded-md border border-slate-600 px-3 py-1 text-xs text-slate-300 hover:bg-slate-800"
          >
            + Add param
          </button>
        </div>
        <p className="mt-1 text-[11px] text-slate-500">
          Common: temperature, top_p, max_tokens, thinking_budget. Values parse
          as JSON when possible.
        </p>
      </div>

      <SaveBar
        dirty={dirty}
        saving={saving}
        onSave={save}
        onReset={() => {
          setLocal(value);
          setParamRows(paramsToRows(value.params));
        }}
        error={error}
      />
    </section>
  );
}
