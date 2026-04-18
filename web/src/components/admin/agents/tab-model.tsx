"use client";

import { useEffect, useMemo, useState } from "react";
import type {
  AgentModelSpec,
  CatalogModel,
  ThinkingLevel,
} from "@/types";
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

  // Only offer enabled models; dedupe by model_id (same id may appear under
  // multiple providers, e.g. gpt-4o via OpenAI and OpenRouter — the router
  // resolves that at runtime).
  const modelOptions = useMemo(() => {
    const seen = new Set<string>();
    const out: { value: string; label: string }[] = [];
    for (const m of models) {
      if (!m.enabled) continue;
      if (seen.has(m.model_id)) continue;
      seen.add(m.model_id);
      out.push({
        value: m.model_id,
        label:
          m.display_name && m.display_name !== m.model_id
            ? `${m.display_name} — ${m.model_id}`
            : m.model_id,
      });
    }
    out.sort((a, b) => a.label.localeCompare(b.label));
    return out;
  }, [models]);

  const knownIds = useMemo(
    () => new Set(modelOptions.map((o) => o.value)),
    [modelOptions],
  );

  // When a saved primary or fallback references a model that is no longer
  // enabled / present in the catalog, show it anyway so the user isn't
  // silently losing configuration — just tag it "(missing)".
  const primaryOptions = useMemo(() => {
    const opts = modelOptions.slice();
    if (local.primary && !knownIds.has(local.primary)) {
      opts.unshift({
        value: local.primary,
        label: `${local.primary} (not in catalog)`,
      });
    }
    return opts;
  }, [modelOptions, knownIds, local.primary]);

  const fallbackOptions = useMemo(
    () => modelOptions.filter((o) => !local.fallbacks.includes(o.value)),
    [modelOptions, local.fallbacks],
  );

  function addFallback(modelId: string) {
    if (!modelId) return;
    if (local.fallbacks.includes(modelId)) return;
    setLocal({ ...local, fallbacks: [...local.fallbacks, modelId] });
  }

  function removeFallback(idx: number) {
    const next = local.fallbacks.slice();
    next.splice(idx, 1);
    setLocal({ ...local, fallbacks: next });
  }

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
        <select
          className={INPUT_CLS}
          value={local.primary ?? ""}
          onChange={(e) =>
            setLocal({ ...local, primary: e.target.value || null })
          }
          disabled={modelOptions.length === 0 && !local.primary}
        >
          <option value="">(inherit default)</option>
          {primaryOptions.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        {modelOptions.length === 0 && (
          <p className="mt-1 text-[11px] text-amber-400">
            No models configured. Add providers + models in{" "}
            <span className="font-mono">/admin/models</span> first.
          </p>
        )}
      </div>

      <div>
        <label className={LABEL_CLS}>Fallbacks</label>
        <div className="flex flex-wrap items-center gap-1.5 rounded-md border border-slate-600 bg-slate-900 px-2 py-1.5">
          {local.fallbacks.map((mid, i) => {
            const missing = !knownIds.has(mid);
            return (
              <span
                key={`${mid}-${i}`}
                className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs ${
                  missing
                    ? "border-amber-600/60 bg-amber-950/40 text-amber-200"
                    : "border-slate-600 bg-slate-800 text-slate-200"
                }`}
                title={missing ? "Not in catalog" : undefined}
              >
                {mid}
                <button
                  type="button"
                  onClick={() => removeFallback(i)}
                  className="text-slate-400 hover:text-red-300"
                  aria-label={`Remove ${mid}`}
                >
                  ×
                </button>
              </span>
            );
          })}
          {local.fallbacks.length === 0 && (
            <span className="px-1 text-xs text-slate-500">
              No fallbacks set
            </span>
          )}
        </div>
        <select
          className={`${INPUT_CLS} mt-2`}
          value=""
          onChange={(e) => {
            addFallback(e.target.value);
            e.target.value = "";
          }}
          disabled={fallbackOptions.length === 0}
        >
          <option value="">
            {fallbackOptions.length === 0
              ? "All configured models already selected"
              : "+ Add fallback model"}
          </option>
          {fallbackOptions.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
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
