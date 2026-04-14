"use client";

/**
 * Create/edit form for a catalog Model under a Provider.
 */

import { useMemo, useState } from "react";
import type {
  Capabilities,
  CatalogModel,
  ModelCost,
  ModelCreate,
  ModelParams,
  PresetModel,
  Presets,
  Provider,
} from "@/types";
import { INPUT_CLS, LABEL_CLS, Toggle, ErrorBanner } from "./shared";

interface ModelFormProps {
  provider: Provider;
  presets: Presets | null;
  initial: CatalogModel | null;
  onSubmit: (body: ModelCreate) => Promise<void>;
  onCancel: () => void;
}

const DEFAULT_CAPS: Capabilities = {
  text: true,
  vision: false,
  tools: false,
  reasoning: false,
  streaming: true,
};

const DEFAULT_PARAMS: ModelParams = {
  temperature: null,
  top_p: null,
  max_tokens: null,
  thinking_budget: null,
  extra: {},
};

const DEFAULT_COST: ModelCost = {
  input_per_mtok: null,
  output_per_mtok: null,
  cache_read_per_mtok: null,
  cache_write_per_mtok: null,
};

function numOrNull(v: string): number | null {
  if (!v.trim()) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export function ModelForm({
  provider,
  presets,
  initial,
  onSubmit,
  onCancel,
}: ModelFormProps) {
  const isEdit = !!initial;

  const providerPresets: PresetModel[] = useMemo(
    () => presets?.providers?.[provider.kind]?.models ?? [],
    [presets, provider.kind],
  );

  const [modelId, setModelId] = useState(initial?.model_id ?? "");
  const [displayName, setDisplayName] = useState(initial?.display_name ?? "");
  const [contextWindow, setContextWindow] = useState<string>(
    initial?.context_window != null ? String(initial.context_window) : "",
  );
  const [maxOutput, setMaxOutput] = useState<string>(
    initial?.max_output_tokens != null
      ? String(initial.max_output_tokens)
      : "",
  );
  const [caps, setCaps] = useState<Capabilities>(
    initial?.capabilities ?? DEFAULT_CAPS,
  );
  const [temperature, setTemperature] = useState<string>(
    initial?.params?.temperature != null
      ? String(initial.params.temperature)
      : "",
  );
  const [topP, setTopP] = useState<string>(
    initial?.params?.top_p != null ? String(initial.params.top_p) : "",
  );
  const [maxTokens, setMaxTokens] = useState<string>(
    initial?.params?.max_tokens != null
      ? String(initial.params.max_tokens)
      : "",
  );
  const [thinkingBudget, setThinkingBudget] = useState<string>(
    initial?.params?.thinking_budget != null
      ? String(initial.params.thinking_budget)
      : "",
  );
  const [costInput, setCostInput] = useState<string>(
    initial?.cost?.input_per_mtok != null
      ? String(initial.cost.input_per_mtok)
      : "",
  );
  const [costOutput, setCostOutput] = useState<string>(
    initial?.cost?.output_per_mtok != null
      ? String(initial.cost.output_per_mtok)
      : "",
  );
  const [costCacheRead, setCostCacheRead] = useState<string>(
    initial?.cost?.cache_read_per_mtok != null
      ? String(initial.cost.cache_read_per_mtok)
      : "",
  );
  const [costCacheWrite, setCostCacheWrite] = useState<string>(
    initial?.cost?.cache_write_per_mtok != null
      ? String(initial.cost.cache_write_per_mtok)
      : "",
  );
  const [notes, setNotes] = useState(initial?.notes ?? "");
  const [enabled, setEnabled] = useState(initial?.enabled ?? true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const currentPreset = useMemo(
    () => providerPresets.find((p) => p.model_id === modelId) ?? null,
    [providerPresets, modelId],
  );

  function applyPreset(preset: PresetModel) {
    setModelId(preset.model_id);
    if (!displayName.trim() || displayName === modelId) {
      setDisplayName(preset.display_name);
    }
    if (preset.context_window != null) {
      setContextWindow(String(preset.context_window));
    }
    if (preset.max_output_tokens != null) {
      setMaxOutput(String(preset.max_output_tokens));
    }
    if (preset.capabilities) {
      setCaps({ ...DEFAULT_CAPS, ...caps, ...preset.capabilities });
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!modelId.trim()) {
      setError("Model ID is required.");
      return;
    }

    const body: ModelCreate = {
      provider_id: provider.id,
      model_id: modelId.trim(),
      display_name: displayName.trim() || modelId.trim(),
      enabled,
      context_window: numOrNull(contextWindow),
      max_output_tokens: numOrNull(maxOutput),
      capabilities: caps,
      params: {
        ...DEFAULT_PARAMS,
        temperature: numOrNull(temperature),
        top_p: numOrNull(topP),
        max_tokens: numOrNull(maxTokens),
        thinking_budget: numOrNull(thinkingBudget),
      },
      cost: {
        input_per_mtok: numOrNull(costInput),
        output_per_mtok: numOrNull(costOutput),
        cache_read_per_mtok: numOrNull(costCacheRead),
        cache_write_per_mtok: numOrNull(costCacheWrite),
      },
      notes,
    };
    if (isEdit) {
      // For edits, provider_id is not part of ModelUpdate but harmless.
      delete (body as Partial<ModelCreate>).provider_id;
    }

    setSubmitting(true);
    setError(null);
    try {
      await onSubmit(body);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save model");
    } finally {
      setSubmitting(false);
    }
  }

  const datalistId = `presets-${provider.id}`;

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <ErrorBanner error={error} />

      {providerPresets.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-slate-700 bg-slate-900/60 p-3">
          <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
            Pick from presets
          </span>
          <select
            className={`${INPUT_CLS} max-w-xs`}
            value=""
            onChange={(e) => {
              const p = providerPresets.find(
                (pp) => pp.model_id === e.target.value,
              );
              if (p) applyPreset(p);
            }}
          >
            <option value="">Choose a preset...</option>
            {providerPresets.map((p) => (
              <option key={p.model_id} value={p.model_id}>
                {p.display_name} ({p.model_id})
              </option>
            ))}
          </select>
          {currentPreset && (
            <span className="text-xs text-slate-500">
              Matched preset: {currentPreset.display_name}
            </span>
          )}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className={LABEL_CLS}>Model ID *</label>
          <input
            className={`${INPUT_CLS} font-mono`}
            value={modelId}
            onChange={(e) => setModelId(e.target.value)}
            placeholder="gpt-4o"
            required
            list={datalistId}
          />
          <datalist id={datalistId}>
            {providerPresets.map((p) => (
              <option key={p.model_id} value={p.model_id}>
                {p.display_name}
              </option>
            ))}
          </datalist>
        </div>
        <div>
          <label className={LABEL_CLS}>Display name</label>
          <input
            className={INPUT_CLS}
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder={currentPreset?.display_name ?? modelId}
          />
        </div>
        <div>
          <label className={LABEL_CLS}>Context window</label>
          <input
            className={INPUT_CLS}
            type="number"
            value={contextWindow}
            onChange={(e) => setContextWindow(e.target.value)}
            placeholder={
              currentPreset?.context_window
                ? String(currentPreset.context_window)
                : "e.g. 128000"
            }
          />
        </div>
        <div>
          <label className={LABEL_CLS}>Max output tokens</label>
          <input
            className={INPUT_CLS}
            type="number"
            value={maxOutput}
            onChange={(e) => setMaxOutput(e.target.value)}
            placeholder={
              currentPreset?.max_output_tokens
                ? String(currentPreset.max_output_tokens)
                : "e.g. 4096"
            }
          />
        </div>
      </div>

      <div>
        <label className={LABEL_CLS}>Capabilities</label>
        <div className="flex flex-wrap gap-4 rounded-md border border-slate-700 bg-slate-900/60 p-3">
          {(Object.keys(DEFAULT_CAPS) as (keyof Capabilities)[]).map((k) => (
            <Toggle
              key={k}
              checked={caps[k]}
              onChange={(v) => setCaps((c) => ({ ...c, [k]: v }))}
              label={k}
            />
          ))}
        </div>
      </div>

      <details className="rounded-md border border-slate-700 bg-slate-900/60">
        <summary className="cursor-pointer px-4 py-2 text-sm font-semibold text-slate-200 hover:bg-slate-800/60">
          Params
        </summary>
        <div className="grid gap-4 border-t border-slate-700 p-4 sm:grid-cols-2">
          <div>
            <label className={LABEL_CLS}>Temperature</label>
            <input
              className={INPUT_CLS}
              type="number"
              step="0.1"
              value={temperature}
              onChange={(e) => setTemperature(e.target.value)}
            />
          </div>
          <div>
            <label className={LABEL_CLS}>Top P</label>
            <input
              className={INPUT_CLS}
              type="number"
              step="0.01"
              value={topP}
              onChange={(e) => setTopP(e.target.value)}
            />
          </div>
          <div>
            <label className={LABEL_CLS}>Max tokens</label>
            <input
              className={INPUT_CLS}
              type="number"
              value={maxTokens}
              onChange={(e) => setMaxTokens(e.target.value)}
            />
          </div>
          <div>
            <label className={LABEL_CLS}>Thinking budget</label>
            <input
              className={INPUT_CLS}
              type="number"
              value={thinkingBudget}
              onChange={(e) => setThinkingBudget(e.target.value)}
            />
          </div>
        </div>
      </details>

      <details className="rounded-md border border-slate-700 bg-slate-900/60">
        <summary className="cursor-pointer px-4 py-2 text-sm font-semibold text-slate-200 hover:bg-slate-800/60">
          Cost (per 1M tokens, USD)
        </summary>
        <div className="grid gap-4 border-t border-slate-700 p-4 sm:grid-cols-2">
          <div>
            <label className={LABEL_CLS}>Input / MTok</label>
            <input
              className={INPUT_CLS}
              type="number"
              step="0.01"
              value={costInput}
              onChange={(e) => setCostInput(e.target.value)}
            />
          </div>
          <div>
            <label className={LABEL_CLS}>Output / MTok</label>
            <input
              className={INPUT_CLS}
              type="number"
              step="0.01"
              value={costOutput}
              onChange={(e) => setCostOutput(e.target.value)}
            />
          </div>
          <div>
            <label className={LABEL_CLS}>Cache read / MTok</label>
            <input
              className={INPUT_CLS}
              type="number"
              step="0.01"
              value={costCacheRead}
              onChange={(e) => setCostCacheRead(e.target.value)}
            />
          </div>
          <div>
            <label className={LABEL_CLS}>Cache write / MTok</label>
            <input
              className={INPUT_CLS}
              type="number"
              step="0.01"
              value={costCacheWrite}
              onChange={(e) => setCostCacheWrite(e.target.value)}
            />
          </div>
        </div>
      </details>

      <div>
        <label className={LABEL_CLS}>Notes</label>
        <textarea
          className={INPUT_CLS}
          rows={2}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Optional notes"
        />
      </div>

      <Toggle checked={enabled} onChange={setEnabled} label="Enabled" />

      <div className="flex justify-end gap-3 border-t border-slate-700 pt-3">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-md border border-slate-600 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={submitting}
          className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          {submitting ? "Saving..." : isEdit ? "Save changes" : "Create model"}
        </button>
      </div>
    </form>
  );
}
