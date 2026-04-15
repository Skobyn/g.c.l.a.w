"use client";

/**
 * Create/edit form for a model Provider.
 * Used inside a Modal in /admin/models.
 *
 * API-key storage modes:
 *  - `sm_store`  — NEW: paste a value, client writes to Secret Manager
 *                  via POST /admin/secrets, then saves the returned path
 *                  on the provider (kind=sm).
 *  - `literal`   — stored in Firestore (legacy/local dev).
 *  - `env`       — points at an env var name.
 *  - `sm_path`   — advanced: paste a pre-existing SM resource path.
 *
 * The persisted provider.api_key.kind is always one of
 * "literal" | "env" | "sm" — sm_store and sm_path both map to "sm".
 */

import { useEffect, useMemo, useState } from "react";
import { useApiClient } from "@/lib/api-client";
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

type KeyMode = "sm_store" | "literal" | "env" | "sm_path";

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

const SM_NAME_RE = /^watson-[a-z0-9-]+$/;

function slugifyProviderName(name: string): string {
  const base = name
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
  return base || "provider";
}

function defaultSecretName(providerName: string): string {
  const slug = slugifyProviderName(providerName);
  return `watson-${slug}-api-key`;
}

function extractSecretNameFromPath(path: string | null): string | null {
  if (!path) return null;
  // projects/{project}/secrets/{name}/versions/{version}
  const m = path.match(/\/secrets\/([^/]+)(\/|$)/);
  return m ? m[1] : null;
}

function extractProjectFromPath(path: string | null): string | null {
  if (!path) return null;
  const m = path.match(/^projects\/([^/]+)\//);
  return m ? m[1] : null;
}

function smConsoleUrl(name: string, project: string): string {
  return `https://console.cloud.google.com/security/secret-manager/secret/${encodeURIComponent(
    name,
  )}/versions?project=${encodeURIComponent(project)}`;
}

export function ProviderForm({
  initial,
  presets,
  onSubmit,
  onCancel,
}: ProviderFormProps) {
  const api = useApiClient();
  const isEdit = !!initial;
  const [name, setName] = useState(initial?.name ?? "");
  const [kind, setKind] = useState<ProviderKind>(initial?.kind ?? "openai");
  const [baseUrl, setBaseUrl] = useState(initial?.base_url ?? "");
  const [enabled, setEnabled] = useState(initial?.enabled ?? true);

  const initialApiKey: ApiKeySpec | null = initial?.api_key ?? null;
  const isMaskedLiteral =
    isEdit && initialApiKey?.kind === "literal" && initialApiKey.value === "***";
  const existingSMName = useMemo(
    () =>
      initialApiKey?.kind === "sm"
        ? extractSecretNameFromPath(initialApiKey.value)
        : null,
    [initialApiKey],
  );
  const existingSMProject = useMemo(
    () =>
      initialApiKey?.kind === "sm"
        ? extractProjectFromPath(initialApiKey.value)
        : null,
    [initialApiKey],
  );

  // Initial mode selection. Default is sm_store for new providers;
  // edits reflect the existing shape.
  const initialMode: KeyMode = (() => {
    if (!isEdit) return "sm_store";
    if (initialApiKey?.kind === "literal") return "literal";
    if (initialApiKey?.kind === "env") return "env";
    if (initialApiKey?.kind === "sm") return "sm_path";
    return "sm_store";
  })();
  const [mode, setMode] = useState<KeyMode>(initialMode);

  // Values per mode
  const [replaceKey, setReplaceKey] = useState(false);
  const [literalValue, setLiteralValue] = useState(
    initialApiKey?.kind === "literal" && !isMaskedLiteral
      ? initialApiKey.value
      : "",
  );
  const [envName, setEnvName] = useState(
    initialApiKey?.kind === "env" ? initialApiKey.value : "",
  );
  const [smPath, setSmPath] = useState(
    initialApiKey?.kind === "sm" ? initialApiKey.value : "",
  );

  // sm_store mode state
  const [smStoreValue, setSmStoreValue] = useState("");
  const [smStoreName, setSmStoreName] = useState<string>(() =>
    defaultSecretName(initial?.name ?? ""),
  );
  const [smStoreNameDirty, setSmStoreNameDirty] = useState(false);
  const [rotateValue, setRotateValue] = useState("");
  const [rotating, setRotating] = useState(false);
  const [rotateMsg, setRotateMsg] = useState<string | null>(null);

  const [showKey, setShowKey] = useState(false);
  const [headerRows, setHeaderRows] = useState<HeaderRow[]>(() => {
    const entries = Object.entries(initial?.default_headers ?? {});
    return entries.length > 0
      ? entries.map(([key, value]) => ({ key, value }))
      : [];
  });

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progressNote, setProgressNote] = useState<string | null>(null);

  const basePlaceholder = useMemo(() => {
    return presets?.providers?.[kind]?.base_url_default ?? "";
  }, [presets, kind]);

  // Keep default SM name in sync with provider name until user edits it.
  useEffect(() => {
    if (mode === "sm_store" && !smStoreNameDirty && !isEdit) {
      setSmStoreName(defaultSecretName(name));
    }
  }, [name, mode, smStoreNameDirty, isEdit]);

  const allowEmptyKey = kind === "google_vertex" || kind === "ollama";

  async function handleRotate() {
    if (!existingSMName) return;
    if (!rotateValue.trim()) {
      setRotateMsg("Paste a new value to rotate.");
      return;
    }
    setRotating(true);
    setRotateMsg(null);
    try {
      const res = await api.rotateSecret(existingSMName, rotateValue.trim());
      setRotateMsg(
        `Rotated. New version ${res.version_id} — the provider keeps ` +
          `pointing at /versions/latest.`,
      );
      setRotateValue("");
    } catch (err) {
      setRotateMsg(
        err instanceof Error ? err.message : "Rotation failed",
      );
    } finally {
      setRotating(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!name.trim()) {
      setError("Name is required.");
      return;
    }

    let api_key: ApiKeySpec | null | undefined;

    if (mode === "literal") {
      if (isEdit && isMaskedLiteral && !replaceKey) {
        api_key = undefined;
      } else if (!literalValue.trim()) {
        if (allowEmptyKey) {
          api_key = null;
        } else {
          setError("API key value is required for this provider kind.");
          return;
        }
      } else {
        api_key = { kind: "literal", value: literalValue.trim() };
      }
    } else if (mode === "env") {
      if (!envName.trim()) {
        setError("Env var name is required.");
        return;
      }
      api_key = { kind: "env", value: envName.trim() };
    } else if (mode === "sm_path") {
      if (!smPath.trim()) {
        setError("Secret Manager resource path is required.");
        return;
      }
      api_key = { kind: "sm", value: smPath.trim() };
    } else {
      // sm_store
      if (isEdit && initialApiKey?.kind === "sm" && !replaceKey) {
        // In edit mode, if the user didn't check replace, leave untouched.
        api_key = undefined;
      } else {
        if (!smStoreValue.trim()) {
          setError("Paste the API key value to store in Secret Manager.");
          return;
        }
        if (!SM_NAME_RE.test(smStoreName)) {
          setError(
            "Secret name must match /^watson-[a-z0-9-]+$/ (lowercase, digits, hyphens; watson- prefix).",
          );
          return;
        }
        // Step 1: write to Secret Manager.
        setSubmitting(true);
        setProgressNote("Writing secret to Secret Manager...");
        try {
          const res = await api.writeSecret({
            name: smStoreName,
            value: smStoreValue.trim(),
          });
          api_key = { kind: "sm", value: res.path };
        } catch (err) {
          setSubmitting(false);
          setProgressNote(null);
          setError(
            err instanceof Error
              ? `Secret Manager write failed: ${err.message}`
              : "Secret Manager write failed",
          );
          return;
        }
      }
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
    setProgressNote(
      mode === "sm_store" && api_key && api_key.kind === "sm"
        ? "Saving provider with Secret Manager path..."
        : null,
    );
    try {
      await onSubmit(body);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save provider");
    } finally {
      setSubmitting(false);
      setProgressNote(null);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <ErrorBanner error={error} />
      {progressNote && (
        <div className="rounded-md border border-indigo-700 bg-indigo-900/30 px-3 py-2 text-xs text-indigo-200">
          {progressNote}
        </div>
      )}

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
          {((isEdit && initialApiKey?.kind === "sm" && mode === "sm_store") ||
            (isEdit && isMaskedLiteral && mode === "literal")) && (
            <label className="flex cursor-pointer items-center gap-2 text-xs text-slate-400">
              <input
                type="checkbox"
                checked={replaceKey}
                onChange={(e) => {
                  setReplaceKey(e.target.checked);
                  if (!e.target.checked) {
                    setLiteralValue("");
                    setSmStoreValue("");
                  }
                }}
                className="h-3.5 w-3.5 rounded border-slate-600 bg-slate-900 text-indigo-500"
              />
              Replace key
            </label>
          )}
        </div>

        <div className="mb-3">
          <label className={LABEL_CLS}>Storage mode</label>
          <select
            className={INPUT_CLS}
            value={mode}
            onChange={(e) => setMode(e.target.value as KeyMode)}
          >
            <option value="sm_store">
              Store in Secret Manager (recommended)
            </option>
            <option value="literal">Literal (stored in Firestore)</option>
            <option value="env">Env var</option>
            <option value="sm_path">Secret Manager (existing path)</option>
          </select>
        </div>

        {mode === "sm_store" && (
          <div className="space-y-3">
            {isEdit && initialApiKey?.kind === "sm" && existingSMName ? (
              <div className="space-y-3 rounded border border-slate-700 bg-slate-900/50 p-3">
                <div>
                  <label className={LABEL_CLS}>Current secret</label>
                  <div className="flex items-center gap-2">
                    <input
                      className={INPUT_CLS}
                      value={initialApiKey.value}
                      readOnly
                    />
                    {existingSMProject && (
                      <a
                        href={smConsoleUrl(existingSMName, existingSMProject)}
                        target="_blank"
                        rel="noreferrer"
                        className="whitespace-nowrap rounded-md border border-slate-600 px-3 py-2 text-xs text-indigo-300 hover:bg-slate-800"
                      >
                        View in SM console
                      </a>
                    )}
                  </div>
                  <p className="mt-1 text-xs text-slate-500">
                    The provider points at <span className="font-mono">/versions/latest</span>,
                    so rotation takes effect immediately — no provider edit needed.
                  </p>
                </div>

                <div className="rounded border border-slate-700 bg-slate-950 p-3">
                  <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
                    Rotate key
                  </div>
                  <div className="flex gap-2">
                    <input
                      className={INPUT_CLS}
                      type={showKey ? "text" : "password"}
                      value={rotateValue}
                      onChange={(e) => setRotateValue(e.target.value)}
                      placeholder="paste new value..."
                    />
                    <button
                      type="button"
                      onClick={() => setShowKey((s) => !s)}
                      className="rounded-md border border-slate-600 px-3 text-xs text-slate-300 hover:bg-slate-800"
                    >
                      {showKey ? "Hide" : "Show"}
                    </button>
                    <button
                      type="button"
                      onClick={handleRotate}
                      disabled={rotating || !rotateValue.trim()}
                      className="whitespace-nowrap rounded-md bg-indigo-600 px-3 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
                    >
                      {rotating ? "Rotating..." : "Rotate"}
                    </button>
                  </div>
                  {rotateMsg && (
                    <p className="mt-2 text-xs text-slate-400">{rotateMsg}</p>
                  )}
                </div>

                {replaceKey && (
                  <div>
                    <p className="text-xs text-amber-400">
                      Replace key mode is for pointing the provider at a
                      different secret. To just update the value, use Rotate
                      above.
                    </p>
                  </div>
                )}
              </div>
            ) : (
              <>
                <div>
                  <label className={LABEL_CLS}>API key value *</label>
                  <div className="flex gap-2">
                    <input
                      className={INPUT_CLS}
                      type={showKey ? "text" : "password"}
                      value={smStoreValue}
                      onChange={(e) => setSmStoreValue(e.target.value)}
                      placeholder="sk-..."
                    />
                    <button
                      type="button"
                      onClick={() => setShowKey((s) => !s)}
                      className="rounded-md border border-slate-600 px-3 text-xs text-slate-300 hover:bg-slate-800"
                    >
                      {showKey ? "Hide" : "Show"}
                    </button>
                  </div>
                </div>
                <div>
                  <label className={LABEL_CLS}>Secret name *</label>
                  <input
                    className={INPUT_CLS}
                    value={smStoreName}
                    onChange={(e) => {
                      setSmStoreName(e.target.value);
                      setSmStoreNameDirty(true);
                    }}
                    pattern="^watson-[a-z0-9-]+$"
                    title="Must match ^watson-[a-z0-9-]+$"
                  />
                  <p className="mt-1 text-xs text-slate-500">
                    Stored in Secret Manager with labels{" "}
                    <span className="font-mono">app=watson, kind=api-key</span>.
                    The provider will be saved with the{" "}
                    <span className="font-mono">/versions/latest</span> path.
                  </p>
                </div>
              </>
            )}
          </div>
        )}

        {mode === "literal" && (
          <div>
            <label className={LABEL_CLS}>Value</label>
            {isEdit && isMaskedLiteral && !replaceKey ? (
              <input className={INPUT_CLS} value="***" readOnly disabled />
            ) : (
              <div className="flex gap-2">
                <input
                  className={INPUT_CLS}
                  type={showKey ? "text" : "password"}
                  value={literalValue}
                  onChange={(e) => setLiteralValue(e.target.value)}
                  placeholder={
                    allowEmptyKey
                      ? "(optional — ADC / no-auth)"
                      : "sk-..."
                  }
                />
                <button
                  type="button"
                  onClick={() => setShowKey((s) => !s)}
                  className="rounded-md border border-slate-600 px-3 text-xs text-slate-300 hover:bg-slate-800"
                >
                  {showKey ? "Hide" : "Show"}
                </button>
              </div>
            )}
            <p className="mt-1 text-xs text-slate-500">
              Stored in Firestore. Prefer{" "}
              <span className="font-mono">Store in Secret Manager</span> for
              production credentials.
            </p>
          </div>
        )}

        {mode === "env" && (
          <div>
            <label className={LABEL_CLS}>Env var name *</label>
            <input
              className={INPUT_CLS}
              value={envName}
              onChange={(e) => setEnvName(e.target.value)}
              placeholder="OPENAI_API_KEY"
            />
          </div>
        )}

        {mode === "sm_path" && (
          <div>
            <label className={LABEL_CLS}>Secret Manager resource path *</label>
            <input
              className={INPUT_CLS}
              value={smPath}
              onChange={(e) => setSmPath(e.target.value)}
              placeholder="projects/PROJECT_ID/secrets/SECRET_NAME/versions/latest"
            />
            <p className="mt-1 text-xs text-slate-500">
              Advanced: point at a pre-existing secret. Use{" "}
              <span className="font-mono">Store in Secret Manager</span> if you
              want the UI to create + populate one for you.
            </p>
          </div>
        )}
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

// Re-export for backwards compatibility with anything importing
// ApiKeyKind from this file in tests.
export type { ApiKeyKind };
