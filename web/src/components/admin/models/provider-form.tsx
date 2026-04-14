"use client";

/**
 * Create/edit form for a model Provider.
 * Used inside a Modal in /admin/models.
 */

import { useEffect, useMemo, useState } from "react";
import type {
  ApiKeyKind,
  ApiKeySpec,
  Presets,
  Provider,
  ProviderCreate,
  ProviderKind,
} from "@/types";
import {
  INPUT_CLS,
  LABEL_CLS,
  PROVIDER_KIND_LABELS,
  Toggle,
  ErrorBanner,
} from "./shared";

interface ProviderFormProps {
  initial: Provider | null;
  presets: Presets | null;
  onSubmit: (body: ProviderCreate) => Promise<void>;
  onCancel: () => void;
}

interface HeaderRow {
  key: string;
  value: string;
}

const KINDS: ProviderKind[] = [
  "openai",
  "anthropic",
  "google_gemini",
  "google_vertex",
  "openrouter",
  "ollama",
  "groq",
  "together",
  "custom_openai",
];

export function ProviderForm({
  initial,
  presets,
  onSubmit,
  onCancel,
}: ProviderFormProps) {
  const isEdit = !!initial;
  const [name, setName] = useState(initial?.name ?? "");
  const [kind, setKind] = useState<ProviderKind>(initial?.kind ?? "openai");
  const [baseUrl, setBaseUrl] = useState(initial?.base_url ?? "");
  const [enabled, setEnabled] = useState(initial?.enabled ?? true);

  const initialApiKey: ApiKeySpec | null = initial?.api_key ?? null;
  const isMaskedLiteral =
    isEdit && initialApiKey?.kind === "literal" && initialApiKey.value === "***";
  const [replaceKey, setReplaceKey] = useState(false);
  const [apiKeyKind, setApiKeyKind] = useState<ApiKeyKind>(
    initialApiKey?.kind ?? "literal",
  );
  const [apiKeyValue, setApiKeyValue] = useState(
    initialApiKey && !isMaskedLiteral ? initialApiKey.value : "",
  );
  const [showKey, setShowKey] = useState(false);

  const [headerRows, setHeaderRows] = useState<HeaderRow[]>(() => {
    const entries = Object.entries(initial?.default_headers ?? {});
    return entries.length > 0
      ? entries.map(([key, value]) => ({ key, value }))
      : [];
  });

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const basePlaceholder = useMemo(() => {
    return presets?.providers?.[kind]?.base_url_default ?? "";
  }, [presets, kind]);

  useEffect(() => {
    if (!isEdit && !baseUrl && basePlaceholder) {
      // Leave input empty but placeholder shows default.
    }
  }, [basePlaceholder, baseUrl, isEdit]);

  const allowEmptyKey = kind === "google_vertex" || kind === "ollama";

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      setError("Name is required.");
      return;
    }

    let api_key: ApiKeySpec | null | undefined;
    if (isEdit && isMaskedLiteral && !replaceKey) {
      // Don't touch the key on the server.
      api_key = undefined;
    } else if (!apiKeyValue.trim()) {
      if (allowEmptyKey) {
        api_key = null;
      } else {
        setError("API key value is required for this provider kind.");
        return;
      }
    } else {
      api_key = { kind: apiKeyKind, value: apiKeyValue.trim() };
    }

    const headers: Record<string, string> = {};
    for (const row of headerRows) {
      const k = row.key.trim();
      if (!k) continue;
      headers[k] = row.value;
    }

    const body: ProviderCreate = {
      name: name.trim(),
      kind,
      base_url: baseUrl.trim() ? baseUrl.trim() : null,
      default_headers: headers,
      enabled,
    };
    if (api_key !== undefined) body.api_key = api_key;

    setSubmitting(true);
    setError(null);
    try {
      await onSubmit(body);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save provider");
    } finally {
      setSubmitting(false);
    }
  }

  const keyInputDisabled = isMaskedLiteral && !replaceKey;

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <ErrorBanner error={error} />

      <div>
        <label className={LABEL_CLS}>Name *</label>
        <input
          className={INPUT_CLS}
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. OpenAI (prod)"
          required
        />
      </div>

      <div>
        <label className={LABEL_CLS}>Kind *</label>
        <select
          className={INPUT_CLS}
          value={kind}
          onChange={(e) => setKind(e.target.value as ProviderKind)}
        >
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {PROVIDER_KIND_LABELS[k]}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className={LABEL_CLS}>Base URL</label>
        <input
          className={INPUT_CLS}
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.target.value)}
          placeholder={basePlaceholder || "https://..."}
        />
        {basePlaceholder && (
          <p className="mt-1 text-xs text-slate-500">
            Default for {PROVIDER_KIND_LABELS[kind]}:{" "}
            <span className="font-mono">{basePlaceholder}</span>
          </p>
        )}
      </div>

      <div className="rounded-md border border-slate-700 bg-slate-900/60 p-3">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
            API Key
          </span>
          {isMaskedLiteral && (
            <label className="flex cursor-pointer items-center gap-2 text-xs text-slate-400">
              <input
                type="checkbox"
                checked={replaceKey}
                onChange={(e) => {
                  setReplaceKey(e.target.checked);
                  if (e.target.checked) setApiKeyValue("");
                }}
                className="h-3.5 w-3.5 rounded border-slate-600 bg-slate-900 text-indigo-500"
              />
              Replace key
            </label>
          )}
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          <div>
            <label className={LABEL_CLS}>Kind</label>
            <select
              className={INPUT_CLS}
              value={apiKeyKind}
              onChange={(e) => setApiKeyKind(e.target.value as ApiKeyKind)}
              disabled={isMaskedLiteral && !replaceKey}
            >
              <option value="literal">Literal (stored)</option>
              <option value="env">Env var</option>
              <option value="sm">Secret Manager</option>
            </select>
          </div>
          <div className="sm:col-span-2">
            <label className={LABEL_CLS}>
              {apiKeyKind === "env" ? "Env var name" : "Value"}
            </label>
            {isMaskedLiteral && !replaceKey ? (
              <input
                className={INPUT_CLS}
                value="***"
                readOnly
                disabled
              />
            ) : apiKeyKind === "literal" ? (
              <div className="flex gap-2">
                <input
                  className={INPUT_CLS}
                  type={showKey ? "text" : "password"}
                  value={apiKeyValue}
                  onChange={(e) => setApiKeyValue(e.target.value)}
                  placeholder={
                    allowEmptyKey
                      ? "(optional — ADC / no-auth)"
                      : "sk-..."
                  }
                  disabled={keyInputDisabled}
                />
                <button
                  type="button"
                  onClick={() => setShowKey((s) => !s)}
                  className="rounded-md border border-slate-600 px-3 text-xs text-slate-300 hover:bg-slate-800"
                >
                  {showKey ? "Hide" : "Show"}
                </button>
              </div>
            ) : apiKeyKind === "env" ? (
              <input
                className={INPUT_CLS}
                value={apiKeyValue}
                onChange={(e) => setApiKeyValue(e.target.value)}
                placeholder="OPENAI_API_KEY"
                disabled={keyInputDisabled}
              />
            ) : (
              <input
                className={INPUT_CLS}
                value={apiKeyValue}
                onChange={(e) => setApiKeyValue(e.target.value)}
                placeholder="projects/PROJECT_ID/secrets/SECRET_NAME/versions/latest"
                disabled={keyInputDisabled}
              />
            )}
          </div>
        </div>

        <p className="mt-2 text-xs text-slate-500">
          Literal keys are stored in Firestore (encrypted at rest). Use{" "}
          <span className="font-mono">Env</span> for stronger isolation.
        </p>
      </div>

      <div>
        <div className="mb-1 flex items-center justify-between">
          <label className={LABEL_CLS}>Default headers (optional)</label>
          <button
            type="button"
            onClick={() =>
              setHeaderRows((rows) => [...rows, { key: "", value: "" }])
            }
            className="rounded-md border border-slate-600 px-2 py-0.5 text-xs text-slate-300 hover:bg-slate-800"
          >
            + Add
          </button>
        </div>
        {headerRows.length === 0 && (
          <p className="text-xs text-slate-500">No custom headers.</p>
        )}
        <div className="space-y-2">
          {headerRows.map((row, i) => (
            <div key={i} className="flex gap-2">
              <input
                className={`${INPUT_CLS} flex-1`}
                placeholder="Header-Name"
                value={row.key}
                onChange={(e) =>
                  setHeaderRows((rows) =>
                    rows.map((r, idx) =>
                      idx === i ? { ...r, key: e.target.value } : r,
                    ),
                  )
                }
              />
              <input
                className={`${INPUT_CLS} flex-1`}
                placeholder="value"
                value={row.value}
                onChange={(e) =>
                  setHeaderRows((rows) =>
                    rows.map((r, idx) =>
                      idx === i ? { ...r, value: e.target.value } : r,
                    ),
                  )
                }
              />
              <button
                type="button"
                onClick={() =>
                  setHeaderRows((rows) => rows.filter((_, idx) => idx !== i))
                }
                className="rounded-md border border-slate-600 px-2 text-xs text-slate-300 hover:bg-red-900/40 hover:text-red-300"
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      </div>

      <Toggle
        checked={enabled}
        onChange={setEnabled}
        label="Enabled"
      />

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
          {submitting
            ? "Saving..."
            : isEdit
            ? "Save changes"
            : "Create provider"}
        </button>
      </div>
    </form>
  );
}
