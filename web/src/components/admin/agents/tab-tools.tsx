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
  const unselectedCatalog = enabledCatalog.filter(
    (t) => !selectedIds.includes(t.id),
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

  function addCatalogTool(id: string) {
    if (!id) return;
    if (selectedIds.includes(id)) return;
    setLocal({
      ...local,
      catalog_tool_ids: [...selectedIds, id],
    });
  }

  function removeCatalogTool(id: string) {
    setLocal({
      ...local,
      catalog_tool_ids: selectedIds.filter((tid) => tid !== id),
    });
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
        <div className="flex flex-wrap items-center gap-1.5 rounded-md border border-slate-600 bg-slate-900 px-2 py-1.5">
          {selectedIds.map((id) => {
            const rec = catalog.find((t) => t.id === id);
            const label = rec ? `${rec.name} · ${rec.kind}` : `${id} (missing)`;
            const missing = !rec;
            return (
              <span
                key={id}
                className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs ${
                  missing
                    ? "border-amber-600/60 bg-amber-950/40 text-amber-200"
                    : "border-slate-600 bg-slate-800 text-slate-200"
                }`}
                title={missing ? "Not in catalog" : undefined}
              >
                {label}
                <button
                  type="button"
                  onClick={() => removeCatalogTool(id)}
                  className="text-slate-400 hover:text-red-300"
                  aria-label={`Remove ${label}`}
                >
                  ×
                </button>
              </span>
            );
          })}
          {selectedIds.length === 0 && (
            <span className="px-1 text-xs text-slate-500">
              No catalog tools bound
            </span>
          )}
        </div>
        <select
          className={`${INPUT_CLS} mt-2`}
          value=""
          onChange={(e) => {
            addCatalogTool(e.target.value);
            e.target.value = "";
          }}
          disabled={unselectedCatalog.length === 0}
        >
          <option value="">
            {unselectedCatalog.length === 0
              ? enabledCatalog.length === 0
                ? "No catalog tools configured (go to /admin/tools)"
                : "All configured catalog tools already bound"
              : "+ Add catalog tool"}
          </option>
          {unselectedCatalog.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name} — {t.kind}
            </option>
          ))}
        </select>
        {catalogError && (
          <p className="mt-1 text-[11px] text-red-400">
            Catalog load error: {catalogError}
          </p>
        )}
      </div>

      <div>
        <label className={LABEL_CLS}>Allow (legacy names)</label>
        <ChipInput
          values={local.allow}
          onChange={(v) => setLocal({ ...local, allow: v })}
          placeholder="tool name"
        />
      </div>

      <div>
        <label className={LABEL_CLS}>Deny</label>
        <ChipInput
          values={local.deny}
          onChange={(v) => setLocal({ ...local, deny: v })}
          placeholder="tool name"
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
