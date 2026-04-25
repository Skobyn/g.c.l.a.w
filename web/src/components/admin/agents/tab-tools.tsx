"use client";

import { useEffect, useMemo, useState } from "react";
import type { AgentToolsSpec, ToolRecord } from "@/types";
import { createApiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/auth-context";
import { ChipInput } from "./chip-input";
import {
  INPUT_CLS,
  LABEL_CLS,
  SECTION_CLS,
  SaveBar,
  deepEqual,
} from "./shared";

const PROFILES = ["default", "minimal", "coding", "messaging", "full"] as const;

interface Props {
  value: AgentToolsSpec;
  onSave: (patch: { tools: AgentToolsSpec }) => Promise<void>;
  onDirtyChange: (dirty: boolean) => void;
}

export function TabTools({ value, onSave, onDirtyChange }: Props) {
  const { getIdToken } = useAuth();
  const api = useMemo(() => createApiClient(getIdToken), [getIdToken]);

  const [local, setLocal] = useState<AgentToolsSpec>(value);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [catalog, setCatalog] = useState<ToolRecord[]>([]);
  const [catalogError, setCatalogError] = useState<string | null>(null);

  useEffect(() => {
    setLocal(value);
  }, [value]);

  useEffect(() => {
    let cancelled = false;
    api
      .listTools()
      .then((list) => {
        if (!cancelled) setCatalog(list);
      })
      .catch((e) => {
        if (!cancelled)
          setCatalogError(e instanceof Error ? e.message : "load failed");
      });
    return () => {
      cancelled = true;
    };
  }, [api]);

  const dirty = !deepEqual(local, value);
  useEffect(() => {
    onDirtyChange(dirty);
  }, [dirty, onDirtyChange]);

  const enabledCatalog = catalog.filter((t) => t.enabled);
  const selectedIds = local.catalog_tool_ids || [];
  const orphanIds = selectedIds.filter(
    (id) => !enabledCatalog.some((t) => t.id === id),
  );
  const catalogToolNames = useMemo(
    () => Array.from(new Set(catalog.map((t) => t.name).filter(Boolean))),
    [catalog],
  );

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await onSave({ tools: local });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  function toggleCatalogTool(id: string) {
    setLocal({
      ...local,
      catalog_tool_ids: selectedIds.includes(id)
        ? selectedIds.filter((tid) => tid !== id)
        : [...selectedIds, id],
    });
  }

  function selectAllCatalog() {
    const allIds = enabledCatalog.map((t) => t.id);
    // Preserve any orphan ids (selected but not in catalog) so we don't
    // silently drop them when the user clicks "Select all".
    const merged = Array.from(new Set([...orphanIds, ...allIds]));
    setLocal({ ...local, catalog_tool_ids: merged });
  }

  function clearCatalog() {
    // Keep orphan ids so they don't disappear from the saved value.
    setLocal({ ...local, catalog_tool_ids: orphanIds });
  }

  return (
    <section className={SECTION_CLS}>
      <h2 className="text-lg font-semibold text-slate-100">Tools</h2>
      <p className="text-xs text-slate-500">
        Profile sets a baseline; allow adds legacy tools on top; deny removes
        tools; catalog-selected entries are layered in from{" "}
        <span className="font-mono">/admin/tools</span>.
      </p>

      <div>
        <label className={LABEL_CLS}>Profile</label>
        <select
          className={INPUT_CLS}
          value={local.profile ?? ""}
          onChange={(e) =>
            setLocal({ ...local, profile: e.target.value || null })
          }
        >
          <option value="">(inherit)</option>
          {PROFILES.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className={LABEL_CLS}>Catalog tools</label>
        {enabledCatalog.length === 0 ? (
          <p className="text-xs text-slate-500">
            No catalog tools configured. Add some at{" "}
            <span className="font-mono">/admin/tools</span>.
          </p>
        ) : (
          <>
            <div className="mb-2 flex items-center justify-between text-xs text-slate-400">
              <span>
                {selectedIds.filter((id) => !orphanIds.includes(id)).length} of{" "}
                {enabledCatalog.length} selected
              </span>
              <div className="flex gap-3">
                <button
                  type="button"
                  className="text-indigo-300 hover:text-indigo-200 disabled:opacity-50"
                  onClick={selectAllCatalog}
                  disabled={enabledCatalog.every((t) =>
                    selectedIds.includes(t.id),
                  )}
                >
                  Select all available
                </button>
                <button
                  type="button"
                  className="text-slate-300 hover:text-slate-100 disabled:opacity-50"
                  onClick={clearCatalog}
                  disabled={
                    selectedIds.filter((id) => !orphanIds.includes(id))
                      .length === 0
                  }
                >
                  Clear
                </button>
              </div>
            </div>
            <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
              {enabledCatalog.map((t) => (
                <label
                  key={t.id}
                  className="flex cursor-pointer items-start gap-2 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm hover:border-slate-500"
                >
                  <input
                    type="checkbox"
                    checked={selectedIds.includes(t.id)}
                    onChange={() => toggleCatalogTool(t.id)}
                    className="mt-0.5 h-4 w-4 rounded border-slate-600 bg-slate-900 text-indigo-500 focus:ring-indigo-500"
                  />
                  <div className="min-w-0">
                    <div className="font-mono text-xs text-slate-200">
                      {t.name}
                    </div>
                    <div className="truncate text-[11px] text-slate-500">
                      {t.kind}
                    </div>
                  </div>
                </label>
              ))}
            </div>
          </>
        )}
        {orphanIds.length > 0 && (
          <div className="mt-2 rounded-md border border-amber-600/60 bg-amber-950/30 px-3 py-2 text-[11px] text-amber-200">
            <div className="mb-1 font-medium">
              Bound ids not present in the catalog:
            </div>
            <div className="flex flex-wrap gap-1.5">
              {orphanIds.map((id) => (
                <span
                  key={id}
                  className="inline-flex items-center gap-1 rounded border border-amber-600/60 bg-amber-950/40 px-2 py-0.5 font-mono"
                >
                  {id}
                  <button
                    type="button"
                    onClick={() => toggleCatalogTool(id)}
                    className="text-amber-200/70 hover:text-red-300"
                    aria-label={`Remove ${id}`}
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          </div>
        )}
        {catalogError && (
          <p className="mt-1 text-[11px] text-red-400">
            Catalog load error: {catalogError}
          </p>
        )}
      </div>

      <div>
        <label className={LABEL_CLS}>Allow</label>
        <p className="mb-1 text-[11px] text-slate-500">
          Allowlist by tool-function name. When non-empty, every tool not in
          this list is dropped — including hard-coded manager tools. Suggestions
          come from the catalog (<span className="font-mono">/admin/tools</span>).
        </p>
        <ChipInput
          values={local.allow}
          onChange={(v) => setLocal({ ...local, allow: v })}
          placeholder="tool name"
          suggestions={catalogToolNames}
        />
      </div>

      <div>
        <label className={LABEL_CLS}>Deny</label>
        <p className="mb-1 text-[11px] text-slate-500">
          Blocklist of tool-function names that should never reach this agent —
          applies to hard-coded manager tools and catalog tools alike.
        </p>
        <ChipInput
          values={local.deny}
          onChange={(v) => setLocal({ ...local, deny: v })}
          placeholder="tool name"
          suggestions={catalogToolNames}
        />
      </div>

      <SaveBar
        dirty={dirty}
        saving={saving}
        onSave={save}
        onReset={() => setLocal(value)}
        error={error}
      />
    </section>
  );
}
